import os
import pandas as pd
import configparser
import hashlib
from sqlalchemy.orm import Session
from datetime import datetime

from database import SessionLocal, Job, ProcessedFile, GroupMapping, User, GroupToGroupMapping, Wallet, GroupToWalletMapping, UserToWalletMapping
from queries import get_all_group_to_wallet_mappings, get_all_user_to_wallet_mappings
from auth import create_user, get_user

def get_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

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

    # --- 2. Create DateTime Columns ---
    df['queue_time'] = pd.to_datetime(df[['QueDateYear', 'QueDateMonth', 'QueDateDay', 
                                         'QueDateHour', 'QueDateMinute', 'QueDateSecond']].astype(str).agg('-'.join, axis=1),
                                         format='%Y-%m-%d-%H-%M-%S', errors='coerce')
    df['start_time'] = pd.to_datetime(df[['StartDateYear', 'StartDateMonth', 'StartDateDay', 
                                         'StartDateHour', 'StartDateMinute', 'StartDateSecond']].astype(str).agg('-'.join, axis=1),
                                         format='%Y-%m-%d-%H-%M-%S', errors='coerce')
    df.dropna(subset=['queue_time', 'start_time'], inplace=True)

    # --- 3. Apply Mappings and Business Logic ---
    df['resource_type'] = df['Queue'].apply(lambda x: 'GPU' if 'gpu' in str(x).lower() else 'CPU')

    # Apply group-to-group mappings first
    group_to_group_mappings = {m.source_group: m.target_group for m in db.query(GroupToGroupMapping).all()}
    df['UserGroup'] = df['UserGroup'].apply(lambda x: group_to_group_mappings.get(x, x))

    # Set wallet name based on mappings (user mapping takes precedence)
    df['wallet_name'] = df['UserGroup'] # Default to user group
    group_to_wallet_dict = {m['source_group']: m['wallet_name'] for m in get_all_group_to_wallet_mappings(db)}
    df['wallet_name'] = df.apply(lambda row: group_to_wallet_dict.get(row['UserGroup'], row['wallet_name']), axis=1)
    user_to_wallet_dict = {m['username']: m['wallet_name'] for m in get_all_user_to_wallet_mappings(db)}
    df['wallet_name'] = df.apply(lambda row: user_to_wallet_dict.get(row['UserName'], row['wallet_name']), axis=1)

    # Auto-create users if they don't exist
    unique_users = df['UserName'].unique()
    for username in unique_users:
        if not get_user(db, username):
            print(f"Automatically creating user: {username}")
            create_user(db, username, "default_password_123", role="user")

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
                raw_df = pd.read_csv(file_path, sep='\\s+', header=None, names=column_names, on_bad_lines='skip', engine='python')
                raw_df['source_file'] = filename
                
                clean_df = transform_data(raw_df, db)

                if clean_df.empty:
                    print(f"No valid data found in {filename} after transformation.")
                else:
                    # Get existing job_ids from the database for the current source_file
                    existing_job_ids = {job[0] for job in db.query(Job.job_id).filter(Job.source_file == filename).all()}
                    
                    # Filter out jobs that already exist in the database for this source_file
                    jobs_to_add_df = clean_df[~clean_df['job_id'].isin(existing_job_ids)]

                    if jobs_to_add_df.empty:
                        print(f"No new unique jobs to add from {filename}.")
                    else:
                        jobs_to_add = []
                        for index, row in jobs_to_add_df.iterrows():
                            wallet = db.query(Wallet).filter(Wallet.name == row['wallet_name']).first()
                            if not wallet:
                                wallet = Wallet(name=row['wallet_name'])
                                db.add(wallet)
                                db.commit()
                                db.refresh(wallet)
                                print(f"Created new wallet: {row['wallet_name']}")

                            user = db.query(User).filter(User.username == row['user_name']).first()
                            if not user:
                                print(f"Warning: User {row['user_name']} not found, creating with default password.")
                                create_user(db, row['user_name'], "default_password_123", role="user")
                                user = db.query(User).filter(User.username == row['user_name']).first()

                            jobs_to_add.append(Job(
                                job_id=row['job_id'],
                                job_name=row['job_name'],
                                user_name=row['user_name'],
                                user_group=row['user_group'],
                                queue=row['queue'],
                                job_status=row['job_status'],
                                nodes=row['nodes'],
                                cores=row['cores'],
                                memory=row['memory'],
                                run_time_seconds=row['run_time_seconds'],
                                queue_time=row['queue_time'],
                                start_time=row['start_time'],
                                elapse_limit_seconds=row['elapse_limit_seconds'],
                                resource_type=row['resource_type'],
                                wallet_name=row['wallet_name'],
                                source_file=row['source_file']
                            ))
                        db.add_all(jobs_to_add)
                        db.commit()
                        print(f"Successfully loaded {len(jobs_to_add)} new jobs from {filename}.")

                # Update or create ProcessedFile entry
                current_checksum = calculate_checksum(file_path)
                processed_file_entry = db.query(ProcessedFile).filter(ProcessedFile.filename == filename).first()
                if processed_file_entry:
                    processed_file_entry.checksum = current_checksum
                    processed_file_entry.last_processed = datetime.utcnow()
                else:
                    processed_file_entry = ProcessedFile(filename=filename, checksum=current_checksum)
                    db.add(processed_file_entry)
                db.commit()
                print(f"Updated processed file entry for {filename}.")

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
                    
