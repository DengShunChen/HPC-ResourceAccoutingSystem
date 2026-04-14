import os
import pandas as pd
import configparser
import hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    Job,
    ProcessedFile,
    GroupMapping,
    User,
    GroupToGroupMapping,
    Wallet,
    GroupToWalletMapping,
    UserToWalletMapping,
)
from queries import invalidate_report_caches
from auth import get_password_hash

# 單檔大量寫入時分段 commit；bulk_insert_mappings 無完整 ORM 實例，可略放大 chunk
_JOB_INSERT_CHUNK = 10000
_JOB_ID_YIELD_PER = 8000


def _wallet_mapping_dicts(db: Session) -> tuple[dict[str, str], dict[str, str]]:
    """載入熱路徑直接查 DB，避免經過 Redis 包裝的 queries 快取函式。"""
    group_rows = (
        db.query(GroupToWalletMapping.source_group, Wallet.name)
        .join(Wallet, GroupToWalletMapping.wallet_id == Wallet.id)
        .all()
    )
    group_to_wallet = {sg: name for sg, name in group_rows}
    user_rows = (
        db.query(User.username, Wallet.name)
        .join(UserToWalletMapping, User.id == UserToWalletMapping.user_id)
        .join(Wallet, Wallet.id == UserToWalletMapping.wallet_id)
        .all()
    )
    user_to_wallet = {un: wn for un, wn in user_rows}
    return group_to_wallet, user_to_wallet


def _compose_datetime(
    df: pd.DataFrame,
    year_col: str,
    month_col: str,
    day_col: str,
    hour_col: str,
    minute_col: str,
    second_col: str,
) -> pd.Series:
    """以欄位組裝 timestamp，避免 `agg('-'.join, axis=1)` 在大表上極慢。"""
    y = pd.to_numeric(df[year_col], errors="coerce")
    mo = pd.to_numeric(df[month_col], errors="coerce")
    d = pd.to_numeric(df[day_col], errors="coerce")
    h = pd.to_numeric(df[hour_col], errors="coerce")
    mi = pd.to_numeric(df[minute_col], errors="coerce")
    s = pd.to_numeric(df[second_col], errors="coerce")
    return pd.to_datetime(
        {"year": y, "month": mo, "day": d, "hour": h, "minute": mi, "second": s},
        errors="coerce",
    )


def _analyze_jobs_table(db: Session) -> None:
    """大量寫入後於**目前 Session 所綁定之資料庫**執行 ANALYZE（測試 in-memory 與正式檔案庫皆正確）。"""
    try:
        bind = db.get_bind()
        with bind.connect() as conn:
            conn.execute(text("ANALYZE jobs"))
            conn.commit()
    except Exception as e:
        print(f"ANALYZE jobs skipped: {e}")


def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def _bulk_ensure_wallets_users(db: Session, jobs_df: pd.DataFrame) -> None:
    """預先批次建立本批 jobs 需要的 Wallet / User，避免逐列查詢與 commit。"""
    wallet_names = [w for w in jobs_df["wallet_name"].dropna().unique().tolist() if w != ""]
    if wallet_names:
        have = {w.name for w in db.query(Wallet).filter(Wallet.name.in_(wallet_names)).all()}
        new_w = [Wallet(name=n) for n in wallet_names if n not in have]
        if new_w:
            db.add_all(new_w)
            db.commit()
            for w in new_w:
                print(f"Created new wallet: {w.name}")

    usernames = [u for u in jobs_df["user_name"].dropna().unique().tolist() if u != ""]
    if usernames:
        have_u = {u.username for u in db.query(User).filter(User.username.in_(usernames)).all()}
        missing = [u for u in usernames if u not in have_u]
        for name in missing:
            db.add(
                User(
                    username=name,
                    hashed_password=get_password_hash("default_password_123"),
                    role="user",
                )
            )
            print(f"Automatically creating user: {name}")
        if missing:
            db.commit()


def calculate_checksum(file_path):
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def transform_data(df: pd.DataFrame, db: Session) -> pd.DataFrame:
    """Transforms the raw dataframe into a clean format for the database."""
    # Ensure required date columns exist before proceeding
    date_cols = ['QueDateYear', 'QueDateMonth', 'QueDateDay', 'QueDateHour', 'QueDateMinute', 'QueDateSecond',
                 'StartDateYear', 'StartDateMonth', 'StartDateDay', 'StartDateHour', 'StartDateMinute', 'StartDateSecond']
    if not all(col in df.columns for col in date_cols):
        raise ValueError("One or more required date columns are missing from the input data.")

    # --- 1. Data Cleaning and Type Conversion on Raw Columns ---
    # Clean parenthesized numbers BEFORE renaming and converting to numeric
    df['RunTimeSeconds'] = pd.to_numeric(df['RunTimeSeconds'].astype(str).str.replace(r'[()]', '', regex=True), errors='coerce').fillna(0)
    df['ElapseLimiteSecond'] = pd.to_numeric(df['ElapseLimiteSecond'].astype(str).str.replace(r'[()]', '', regex=True), errors='coerce').fillna(0)
    
    # Handle Memory - assuming it's a number, remove any non-numeric characters just in case
    df['Memory'] = pd.to_numeric(df['Memory'].astype(str).str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0)

    # --- 2. Create DateTime Columns（向量化；避免逐列字串拼接）---
    df["queue_time"] = _compose_datetime(
        df,
        "QueDateYear",
        "QueDateMonth",
        "QueDateDay",
        "QueDateHour",
        "QueDateMinute",
        "QueDateSecond",
    )
    df["start_time"] = _compose_datetime(
        df,
        "StartDateYear",
        "StartDateMonth",
        "StartDateDay",
        "StartDateHour",
        "StartDateMinute",
        "StartDateSecond",
    )
    df.dropna(subset=["queue_time", "start_time"], inplace=True)

    # --- 3. Apply Mappings and Business Logic ---
    qlower = df["Queue"].astype(str).str.lower()
    df["resource_type"] = qlower.str.contains("gpu", na=False).map({True: "GPU", False: "CPU"})

    group_to_group_mappings = {m.source_group: m.target_group for m in db.query(GroupToGroupMapping).all()}
    if group_to_group_mappings:
        df["UserGroup"] = df["UserGroup"].replace(group_to_group_mappings)

    # GroupMapping：一次 join 查回，避免 N+1
    group_to_username = {
        row[0]: row[1]
        for row in db.query(GroupMapping.source_group, User.username)
        .join(User, GroupMapping.target_user_id == User.id)
        .all()
    }
    if group_to_username:
        df["UserName"] = df["UserGroup"].map(group_to_username).fillna(df["UserName"])

    df["wallet_name"] = df["UserGroup"]
    group_to_wallet_dict, user_to_wallet_dict = _wallet_mapping_dicts(db)
    if group_to_wallet_dict:
        df["wallet_name"] = df["UserGroup"].map(group_to_wallet_dict).fillna(df["wallet_name"])
    if user_to_wallet_dict:
        df["wallet_name"] = df["UserName"].map(user_to_wallet_dict).fillna(df["wallet_name"])

    # 自動建帳：一次查已存在者，其餘批次 insert + 單次 commit
    unique_users = [u for u in df["UserName"].dropna().unique() if u != ""]
    if unique_users:
        have = {u.username for u in db.query(User).filter(User.username.in_(unique_users)).all()}
        missing = [u for u in unique_users if u not in have]
        for name in missing:
            db.add(
                User(
                    username=name,
                    hashed_password=get_password_hash("default_password_123"),
                    role="user",
                )
            )
            print(f"Automatically creating user: {name}")
        if missing:
            db.commit()

    # Map job status
    status_map = {'EXT': 'COMPLETED', 'CCL': 'USER_CANCELED'}
    df['JobStatus'] = df['JobStatus'].replace(status_map)

    # --- 4. Rename columns to match database schema ---
    df.rename(columns={
        'JobID': 'job_id',
        'JobName': 'job_name',
        'UserName': 'user_name',
        'UserGroup': 'user_group',
        'Queue': 'queue',
        'JobStatus': 'job_status',
        'Nodes': 'nodes',
        'Cores': 'cores',
        'Memory': 'memory',
        'RunTimeSeconds': 'run_time_seconds',
        'ElapseLimiteSecond': 'elapse_limit_seconds'
    }, inplace=True)
    
    # --- 5. Final Type Casting for Database ---
    df['job_id'] = df['job_id'].astype(str)
    df['run_time_seconds'] = df['run_time_seconds'].astype(int)
    df['elapse_limit_seconds'] = df['elapse_limit_seconds'].astype(int)
    df['nodes'] = pd.to_numeric(df['nodes'], errors='coerce').fillna(0).astype(int)
    df['cores'] = pd.to_numeric(df['cores'], errors='coerce').fillna(0).astype(int)

    # --- 6. Select and Return Final Columns ---
    final_columns = [
        'job_id', 'job_name', 'user_name', 'user_group', 'queue', 'job_status',
        'nodes', 'cores', 'memory', 'run_time_seconds',
        'queue_time', 'start_time', 'elapse_limit_seconds', 'resource_type', 'wallet_name', 'source_file'
    ]
    # Ensure all final columns exist, adding any that might be missing
    for col in final_columns:
        if col not in df.columns:
            df[col] = None # Or a suitable default

    return df[final_columns]

def load_new_data(db: Session = None, specific_file: str = None, force: bool = False):
    """
    Scans the log directory, processes new or modified files, and loads them into the database.
    - Default mode: Scans for new files or files with changed checksums.
    - Specific file mode: Processes only the given file.
    - Force mode: Deletes all existing data for the specified file before reloading.
    """
    config = get_config()
    log_dir = config.get('data', 'log_directory_path')
    column_names = [name.strip() for name in config.get('log_schema', 'column_names').split(',')]

    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        files_to_process = []
        modified_files = []
        # 掃描目錄時已讀過檔案的 checksum 時，寫入階段不重複整檔 SHA256
        checksum_precomputed: dict[str, str] = {}

        if specific_file:
            if os.path.exists(os.path.join(log_dir, specific_file)):
                files_to_process.append(specific_file)
                # If a specific file is forced, treat it as modified for deletion logic
                if force:
                    modified_files.append(specific_file)
            else:
                print(f"Error: Specified file '{specific_file}' not found.")
                return
        else:
            processed_files_db = {pf.filename: pf.checksum for pf in db.query(ProcessedFile).all()}
            all_files_in_dir = sorted([f for f in os.listdir(log_dir) if f.endswith('.out')])

            for filename in all_files_in_dir:
                file_path = os.path.join(log_dir, filename)
                if filename not in processed_files_db:
                    files_to_process.append(filename)
                    print(f"Found new file: {filename}")
                else:
                    current_checksum = calculate_checksum(file_path)
                    checksum_precomputed[filename] = current_checksum
                    if processed_files_db[filename] != current_checksum:
                        files_to_process.append(filename)
                        modified_files.append(filename)
                        print(f"Found modified file: {filename}")

        if not files_to_process:
            print("No new or modified log files to process.")
            return

        print(f"Found {len(files_to_process)} files to process: {files_to_process}")

        for filename in files_to_process:
            file_path = os.path.join(log_dir, filename)
            print(f"Processing {file_path}...")

            # If forcing or if the file was detected as modified, delete existing data first.
            if force or filename in modified_files:
                print(f"Deleting existing data for {filename} before loading...")
                db.query(Job).filter(Job.source_file == filename).delete(synchronize_session=False)
                db.commit()
                print("Existing data for jobs deleted.")

            try:
                raw_df = pd.read_csv(
                    file_path,
                    sep=r"\s+",
                    header=None,
                    names=column_names,
                    on_bad_lines="skip",
                    engine="c",
                )
                raw_df['source_file'] = filename
                
                clean_df = transform_data(raw_df, db)

                if clean_df.empty:
                    print(f"No valid data found in {filename} after transformation.")
                else:
                    # Get existing job_ids from the database for the current source_file（yield_per 降低單次載入尖峰）
                    existing_job_ids = set()
                    for row in db.query(Job.job_id).filter(Job.source_file == filename).yield_per(_JOB_ID_YIELD_PER):
                        existing_job_ids.add(row.job_id)
                    
                    # Filter out jobs that already exist in the database for this source_file
                    jobs_to_add_df = clean_df[~clean_df['job_id'].isin(existing_job_ids)]

                    if jobs_to_add_df.empty:
                        print(f"No new unique jobs to add from {filename}.")
                    else:
                        _bulk_ensure_wallets_users(db, jobs_to_add_df)

                        records = jobs_to_add_df.to_dict("records")
                        for r in records:
                            m = r.get("memory")
                            r["memory"] = "" if m is None or pd.isna(m) else str(m)
                            wn = r.get("wallet_name")
                            if wn is not None and pd.isna(wn):
                                r["wallet_name"] = None
                        n_ins = len(records)
                        for i in range(0, n_ins, _JOB_INSERT_CHUNK):
                            db.bulk_insert_mappings(Job, records[i : i + _JOB_INSERT_CHUNK])
                            db.commit()
                        print(f"Successfully loaded {n_ins} new jobs from {filename}.")
                        _analyze_jobs_table(db)

                # Update or create ProcessedFile entry
                current_checksum = checksum_precomputed.get(filename) or calculate_checksum(
                    file_path
                )
                processed_file_entry = db.query(ProcessedFile).filter(ProcessedFile.filename == filename).first()
                if processed_file_entry:
                    processed_file_entry.checksum = current_checksum
                else:
                    processed_file_entry = ProcessedFile(filename=filename, checksum=current_checksum)
                    db.add(processed_file_entry)
                db.commit()
                print(f"Updated processed file entry for {filename}.")
                invalidate_report_caches()

            except Exception as e:
                db.rollback()
                print(f"Error processing {filename}: {e}")
                import traceback
                traceback.print_exc()

    finally:
        if close_db:
            db.close()

if __name__ == "__main__":
    # Example usage:
    # To load all new/modified files
    # load_new_data()

    # To force reload a specific file
    # load_new_data(specific_file="250718.out", force=True)

    # To process a specific file without forcing (will only add new jobs if checksum changed or file is new)
    load_new_data(specific_file="250718.out")
                    
