import typer
from typing_extensions import Annotated
import os
from datetime import datetime
import pandas as pd

from database import SessionLocal, Base, engine, ProcessedFile, Job # Import Base and engine for Alembic
from data_loader import load_new_data
from auth import create_initial_admin_user, get_user, create_user, verify_password
from queries import get_kpi_data, get_usage_over_time, get_filtered_jobs,     get_all_registered_users, set_user_quota, delete_user,     get_all_group_mappings, add_group_mapping, delete_group_mapping,     generate_accounting_report, create_wallet, delete_wallet, get_all_wallets,     add_group_to_wallet_mapping, delete_group_to_wallet_mapping, get_all_group_to_wallet_mappings,     add_user_to_wallet_mapping, delete_user_to_wallet_mapping, get_all_user_to_wallet_mappings

from alembic.config import Config
from alembic import command

# Create a Typer app
app = typer.Typer(help="運算資源帳務系統指令列工具")

# --- Alembic Configuration Helper ---
def get_alembic_config():
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return alembic_cfg

# --- Helper for DB Session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Authentication for CLI (Simplified) ---
def authenticate_admin_cli(db: SessionLocal):
    username = typer.prompt("Admin Username")
    password = typer.prompt("Admin Password", hide_input=True)
    user = get_user(db, username)
    if not user or not verify_password(password, user.hashed_password) or user.role != "admin":
        typer.secho("Authentication failed: Invalid credentials or not an admin.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    return user

# --- CLI Commands ---

@app.command("init-admin", help="初始化管理員帳號 (首次設定時使用)")
def init_admin_command(
    username: Annotated[str, typer.Argument(help="管理員帳號名稱")],
    password: Annotated[str, typer.Argument(help="管理員密碼")]
):
    db = next(get_db())
    create_initial_admin_user(db, username, password)
    typer.secho(f"Admin user '{username}' setup attempt completed.", fg=typer.colors.GREEN)

@app.command("load-data", help="掃描資料目錄、處理新日誌檔並載入至資料庫。")
def run_data_loader_command(
    file: Annotated[str, typer.Option(help="僅載入特定檔案。")] = None,
    force: Annotated[bool, typer.Option(help="強制重新載入檔案，將會先刪除舊資料。此選項必須與 --file 同時使用。")] = False
):
    """Scans the log directory, processes new files, and loads them into the database."""
    if force and not file:
        typer.secho("錯誤：--force 旗標必須與 --file 選項一同使用。", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho("正在開始資料載入程序...", fg=typer.colors.BLUE)
    db = next(get_db())
    try:
        load_new_data(db=db, specific_file=file, force=force)
        typer.secho("資料載入程序已成功完成。", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"資料載入過程中發生無法預期的錯誤: {e}", fg=typer.colors.RED)
        db.rollback()
        raise typer.Exit(code=1)
    finally:
        db.close()

@app.command("clear-processed-files", help="清除已處理檔案的記錄，以便重新載入所有日誌檔。")
def clear_processed_files_command():
    db = next(get_db())
    try:
        num_deleted = db.query(ProcessedFile).delete()
        db.commit()
        typer.secho(f"Successfully cleared {num_deleted} processed file records.", fg=typer.colors.GREEN)
    except Exception as e:
        db.rollback()
        typer.secho(f"Error clearing processed files: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("clear-jobs", help="清除所有任務資料。")
def clear_jobs_command():
    db = next(get_db())
    try:
        num_deleted = db.query(Job).delete()
        db.commit()
        typer.secho(f"Successfully cleared {num_deleted} job records.", fg=typer.colors.GREEN)
    except Exception as e:
        db.rollback()
        typer.secho(f"Error clearing job records: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-init", help="初始化 Alembic 環境 (首次設定時使用)。")
def alembic_init_command():
    typer.secho("Initializing Alembic environment...", fg=typer.colors.BLUE)
    try:
        # Create alembic directory and env.py
        # command.init will create alembic.ini and the alembic directory
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "alembic")
        command.init(alembic_cfg, "alembic")
        
        # Modify alembic.ini to point to our database
        with open("alembic.ini", "r") as f:
            lines = f.readlines()
        with open("alembic.ini", "w") as f:
            for line in lines:
                if line.strip().startswith("sqlalchemy.url ="):
                    f.write("sqlalchemy.url = sqlite:///./resource_accounting.db\n")
                else:
                    f.write(line)

        # Modify alembic/env.py to import Base and engine from database.py
        env_py_path = os.path.join("alembic", "env.py")
        with open(env_py_path, "r") as f:
            env_lines = f.readlines()
        with open(env_py_path, "w") as f:
            for line in env_lines:
                if "from sqlalchemy import engine_from_config" in line:
                    f.write("from sqlalchemy import engine_from_config\nfrom database import Base, engine\n")
                elif "target_metadata = None" in line:
                    f.write("target_metadata = Base.metadata\n")
                elif "def run_migrations_online():" in line:
                    f.write("    def run_migrations_online():\n        connectable = engine\n")
                elif "    # for example, from your main module" in line:
                    # Remove the example line
                    pass
                elif "    # my_app.models.Base.metadata" in line:
                    # Remove the example line
                    pass
                else:
                    f.write(line)

        typer.secho("Alembic environment initialized successfully. Please review alembic/env.py and alembic.ini.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error initializing Alembic: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-migrate", help="自動產生資料庫遷移腳本。")
def alembic_migrate_command(message: Annotated[str, typer.Option(help="遷移訊息")]):
    typer.secho("Generating Alembic migration script...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=True)
        typer.secho("Alembic migration script generated successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error generating migration script: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade", help="執行資料庫遷移。")
def alembic_upgrade_command(revision: Annotated[str, typer.Option(help="目標版本 (head, base, 或特定版本號)")] = "head"):
    typer.secho(f"Upgrading database to revision {revision}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, revision)
        typer.secho("Database upgrade completed successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history", help="顯示遷移歷史。")
def alembic_history_command():
    typer.secho("Displaying Alembic migration history...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg)
    except Exception as e:
        typer.secho(f"Error displaying history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-current", help="顯示當前資料庫版本。")
def alembic_current_command():
    typer.secho("Displaying current database revision...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.current(alembic_cfg)
    except Exception as e:
        typer.secho(f"Error displaying current revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade", help="降級資料庫版本。")
def alembic_downgrade_command(revision: Annotated[str, typer.Option(help="目標版本 (base, 或特定版本號)")]):
    typer.secho(f"Downgrading database to revision {revision}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, revision)
        typer.secho("Database downgrade completed successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-stamp", help="標記資料庫版本而不執行遷移。")
def alembic_stamp_command(revision: Annotated[str, typer.Option(help="目標版本 (head, base, 或特定版本號)")]):
    typer.secho(f"Stamping database with revision {revision}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, revision)
        typer.secho("Database stamped successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error stamping database: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-heads", help="顯示所有未合併的 head 版本。")
def alembic_heads_command():
    typer.secho("Displaying all unmerged head revisions...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.heads(alembic_cfg)
    except Exception as e:
        typer.secho(f"Error displaying heads: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-show", help="顯示特定遷移腳本的內容。")
def alembic_show_command(revision: Annotated[str, typer.Option(help="版本號")]):
    typer.secho(f"Showing revision {revision}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.show(alembic_cfg, revision)
    except Exception as e:
        typer.secho(f"Error showing revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-merge", help="合併多個 head 版本。")
def alembic_merge_command(revisions: Annotated[str, typer.Option(help="要合併的版本號，用逗號分隔")]):
    typer.secho(f"Merging revisions {revisions}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.merge(alembic_cfg, revisions)
        typer.secho("Revisions merged successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error merging revisions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-edit", help="編輯特定遷移腳本。")
def alembic_edit_command(revision: Annotated[str, typer.Option(help="版本號")]):
    typer.secho(f"Editing revision {revision}...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.edit(alembic_cfg, revision)
        typer.secho("Revision opened for editing.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error editing revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches", help="顯示所有分支。")
def alembic_branches_command():
    typer.secho("Displaying all branches...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg)
    except Exception as e:
        typer.secho(f"Error displaying branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-check", help="檢查是否有未應用的遷移。")
def alembic_check_command():
    typer.secho("Checking for unapplied migrations...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.check(alembic_cfg)
        typer.secho("Check completed.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error during check: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-ensure-version", help="確保資料庫有版本表。")
def alembic_ensure_version_command():
    typer.secho("Ensuring version table exists...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.ensure_version(alembic_cfg)
        typer.secho("Version table ensured.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error ensuring version table: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-list-templates", help="列出可用的 Alembic 模板。")
def alembic_list_templates_command():
    typer.secho("Listing Alembic templates...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.list_templates(alembic_cfg)
    except Exception as e:
        typer.secho(f"Error listing templates: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade-head", help="將資料庫升級到最新版本。")
def alembic_upgrade_head_command():
    typer.secho("Upgrading database to the latest version...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head")
        typer.secho("Database upgraded to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database to head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade-base", help="將資料庫降級到初始版本。")
def alembic_downgrade_base_command():
    typer.secho("Downgrading database to the base version...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, "base")
        typer.secho("Database downgraded to the base version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database to base: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-revision", help="建立新的遷移版本。")
def alembic_revision_command(message: Annotated[str, typer.Option(help="遷移訊息")] = None, autogenerate: Annotated[bool, typer.Option(help="自動生成遷移腳本")] = False):
    typer.secho("Creating new Alembic revision...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
        typer.secho("Alembic revision created successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error creating revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-stamp-head", help="將資料庫標記為最新版本。")
def alembic_stamp_head_command():
    typer.secho("Stamping database to the latest version...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, "head")
        typer.secho("Database stamped to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error stamping database to head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history-verbose", help="顯示詳細的遷移歷史。")
def alembic_history_verbose_command():
    typer.secho("Displaying detailed Alembic migration history...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-current-verbose", help="顯示當前資料庫版本的詳細資訊。")
def alembic_current_verbose_command():
    typer.secho("Displaying detailed current database revision...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.current(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed current revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade-one", help="將資料庫降級一個版本。")
def alembic_downgrade_one_command():
    typer.secho("Downgrading database by one revision...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, "-1")
        typer.secho("Database downgraded by one revision successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database by one revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade-one", help="將資料庫升級一個版本。")
def alembic_upgrade_one_command():
    typer.secho("Upgrading database by one revision...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "+1")
        typer.secho("Database upgraded by one revision successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database by one revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-heads-verbose", help="顯示所有未合併的 head 版本的詳細資訊。")
def alembic_heads_verbose_command():
    typer.secho("Displaying detailed unmerged head revisions...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.heads(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed heads: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-verbose", help="顯示所有分支的詳細資訊。")
def alembic_branches_verbose_command():
    typer.secho("Displaying detailed branches...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-merge-message", help="合併多個 head 版本並提供訊息。")
def alembic_merge_message_command(revisions: Annotated[str, typer.Option(help="要合併的版本號，用逗號分隔")], message: Annotated[str, typer.Option(help="合併訊息")] = None):
    typer.secho(f"Merging revisions {revisions} with message...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.merge(alembic_cfg, revisions, message=message)
        typer.secho("Revisions merged successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error merging revisions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history-limit", help="顯示最近的遷移歷史。")
def alembic_history_limit_command(limit: Annotated[int, typer.Option(help="要顯示的歷史記錄數量")]):
    typer.secho(f"Displaying last {limit} Alembic migration history entries...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, limit=limit)
    except Exception as e:
        typer.secho(f"Error displaying limited history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-show-verbose", help="顯示特定遷移腳本的詳細內容。")
def alembic_show_verbose_command(revision: Annotated[str, typer.Option(help="版本號")]):
    typer.secho(f"Showing revision {revision} in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.show(alembic_cfg, revision, verbose=True)
    except Exception as e:
        typer.secho(f"Error showing detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-edit-message", help="編輯特定遷移腳本並提供訊息。")
def alembic_edit_message_command(revision: Annotated[str, typer.Option(help="版本號")], message: Annotated[str, typer.Option(help="編輯訊息")] = None):
    typer.secho(f"Editing revision {revision} with message...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.edit(alembic_cfg, revision, message=message)
        typer.secho("Revision opened for editing.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error editing revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-limit", help="顯示最近的分支。")
def alembic_branches_limit_command(limit: Annotated[int, typer.Option(help="要顯示的分支數量")]):
    typer.secho(f"Displaying last {limit} Alembic branches...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, limit=limit)
    except Exception as e:
        typer.secho(f"Error displaying limited branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-check-verbose", help="檢查是否有未應用的遷移並顯示詳細資訊。")
def alembic_check_verbose_command():
    typer.secho("Checking for unapplied migrations in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.check(alembic_cfg, verbose=True)
        typer.secho("Check completed.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error during detailed check: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-ensure-version-verbose", help="確保資料庫有版本表並顯示詳細資訊。")
def alembic_ensure_version_verbose_command():
    typer.secho("Ensuring version table exists in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.ensure_version(alembic_cfg, verbose=True)
        typer.secho("Version table ensured.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error ensuring detailed version table: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-list-templates-verbose", help="列出可用的 Alembic 模板並顯示詳細資訊。")
def alembic_list_templates_verbose_command():
    typer.secho("Listing Alembic templates in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.list_templates(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error listing detailed templates: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade-head-verbose", help="將資料庫升級到最新版本並顯示詳細資訊。")
def alembic_upgrade_head_verbose_command():
    typer.secho("Upgrading database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head", verbose=True)
        typer.secho("Database upgraded to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database to detailed head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade-base-verbose", help="將資料庫降級到初始版本並顯示詳細資訊。")
def alembic_downgrade_base_verbose_command():
    typer.secho("Downgrading database to the base version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, "base", verbose=True)
        typer.secho("Database downgraded to the base version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database to detailed base: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-revision-verbose", help="建立新的遷移版本並顯示詳細資訊。")
def alembic_revision_verbose_command(message: Annotated[str, typer.Option(help="遷移訊息")] = None, autogenerate: Annotated[bool, typer.Option(help="自動生成遷移腳本")] = False):
    typer.secho("Creating new Alembic revision in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate, verbose=True)
        typer.secho("Alembic revision created successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error creating detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-stamp-head-verbose", help="將資料庫標記為最新版本並顯示詳細資訊。")
def alembic_stamp_head_verbose_command():
    typer.secho("Stamping database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, "head", verbose=True)
        typer.secho("Database stamped to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error stamping detailed database to head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history-limit-verbose", help="顯示最近的遷移歷史並顯示詳細資訊。")
def alembic_history_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的歷史記錄數量")]):
    typer.secho(f"Displaying last {limit} Alembic migration history entries in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-limit-verbose", help="顯示最近的分支並顯示詳細資訊。")
def alembic_branches_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的分支數量")]):
    typer.secho(f"Displaying last {limit} Alembic branches in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-merge-message-verbose", help="合併多個 head 版本並提供訊息，顯示詳細資訊。")
def alembic_merge_message_verbose_command(revisions: Annotated[str, typer.Option(help="要合併的版本號，用逗號分隔")], message: Annotated[str, typer.Option(help="合併訊息")] = None):
    typer.secho(f"Merging revisions {revisions} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.merge(alembic_cfg, revisions, message=message, verbose=True)
        typer.secho("Revisions merged successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error merging detailed revisions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-edit-message-verbose", help="編輯特定遷移腳本並提供訊息，顯示詳細資訊。")
def alembic_edit_message_verbose_command(revision: Annotated[str, typer.Option(help="版本號")], message: Annotated[str, typer.Option(help="編輯訊息")] = None):
    typer.secho(f"Editing revision {revision} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.edit(alembic_cfg, revision, message=message, verbose=True)
        typer.secho("Revision opened for editing.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error editing detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-verbose", help="顯示所有分支的詳細資訊。")
def alembic_branches_verbose_command():
    typer.secho("Displaying detailed branches...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-check-verbose", help="檢查是否有未應用的遷移並顯示詳細資訊。")
def alembic_check_verbose_command():
    typer.secho("Checking for unapplied migrations in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.check(alembic_cfg, verbose=True)
        typer.secho("Check completed.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error during detailed check: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-ensure-version-verbose", help="確保資料庫有版本表並顯示詳細資訊。")
def alembic_ensure_version_verbose_command():
    typer.secho("Ensuring version table exists in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.ensure_version(alembic_cfg, verbose=True)
        typer.secho("Version table ensured.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error ensuring detailed version table: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-list-templates-verbose", help="列出可用的 Alembic 模板並顯示詳細資訊。")
def alembic_list_templates_verbose_command():
    typer.secho("Listing Alembic templates in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.list_templates(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error listing detailed templates: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade-head-verbose", help="將資料庫升級到最新版本並顯示詳細資訊。")
def alembic_upgrade_head_verbose_command():
    typer.secho("Upgrading database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head", verbose=True)
        typer.secho("Database upgraded to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database to detailed head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade-base-verbose", help="將資料庫降級到初始版本並顯示詳細資訊。")
def alembic_downgrade_base_verbose_command():
    typer.secho("Downgrading database to the base version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, "base", verbose=True)
        typer.secho("Database downgraded to the base version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database to detailed base: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-revision-verbose", help="建立新的遷移版本並顯示詳細資訊。")
def alembic_revision_verbose_command(message: Annotated[str, typer.Option(help="遷移訊息")] = None, autogenerate: Annotated[bool, typer.Option(help="自動生成遷移腳本")] = False):
    typer.secho("Creating new Alembic revision in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate, verbose=True)
        typer.secho("Alembic revision created successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error creating detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-stamp-head-verbose", help="將資料庫標記為最新版本並顯示詳細資訊。")
def alembic_stamp_head_verbose_command():
    typer.secho("Stamping database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, "head", verbose=True)
        typer.secho("Database stamped to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error stamping detailed database to head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history-limit-verbose", help="顯示最近的遷移歷史並顯示詳細資訊。")
def alembic_history_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的歷史記錄數量")]):
    typer.secho(f"Displaying last {limit} Alembic migration history entries in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-limit-verbose", help="顯示最近的分支並顯示詳細資訊。")
def alembic_branches_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的分支數量")]):
    typer.secho(f"Displaying last {limit} Alembic branches in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-merge-message-verbose", help="合併多個 head 版本並提供訊息，顯示詳細資訊。")
def alembic_merge_message_verbose_command(revisions: Annotated[str, typer.Option(help="要合併的版本號，用逗號分隔")], message: Annotated[str, typer.Option(help="合併訊息")] = None):
    typer.secho(f"Merging revisions {revisions} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.merge(alembic_cfg, revisions, message=message, verbose=True)
        typer.secho("Revisions merged successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error merging detailed revisions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-edit-message-verbose", help="編輯特定遷移腳本並提供訊息，顯示詳細資訊。")
def alembic_edit_message_verbose_command(revision: Annotated[str, typer.Option(help="版本號")], message: Annotated[str, typer.Option(help="編輯訊息")] = None):
    typer.secho(f"Editing revision {revision} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.edit(alembic_cfg, revision, message=message, verbose=True)
        typer.secho("Revision opened for editing.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error editing detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-verbose", help="顯示所有分支的詳細資訊。")
def alembic_branches_verbose_command():
    typer.secho("Displaying detailed branches...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-check-verbose", help="檢查是否有未應用的遷移並顯示詳細資訊。")
def alembic_check_verbose_command():
    typer.secho("Checking for unapplied migrations in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.check(alembic_cfg, verbose=True)
        typer.secho("Check completed.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error during detailed check: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-ensure-version-verbose", help="確保資料庫有版本表並顯示詳細資訊。")
def alembic_ensure_version_verbose_command():
    typer.secho("Ensuring version table exists in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.ensure_version(alembic_cfg, verbose=True)
        typer.secho("Version table ensured.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error ensuring detailed version table: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-list-templates-verbose", help="列出可用的 Alembic 模板並顯示詳細資訊。")
def alembic_list_templates_verbose_command():
    typer.secho("Listing Alembic templates in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.list_templates(alembic_cfg, verbose=True)
    except Exception as e:
        typer.secho(f"Error listing detailed templates: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-upgrade-head-verbose", help="將資料庫升級到最新版本並顯示詳細資訊。")
def alembic_upgrade_head_verbose_command():
    typer.secho("Upgrading database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.upgrade(alembic_cfg, "head", verbose=True)
        typer.secho("Database upgraded to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error upgrading database to detailed head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-downgrade-base-verbose", help="將資料庫降級到初始版本並顯示詳細資訊。")
def alembic_downgrade_base_verbose_command():
    typer.secho("Downgrading database to the base version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.downgrade(alembic_cfg, "base", verbose=True)
        typer.secho("Database downgraded to the base version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error downgrading database to detailed base: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-revision-verbose", help="建立新的遷移版本並顯示詳細資訊。")
def alembic_revision_verbose_command(message: Annotated[str, typer.Option(help="遷移訊息")] = None, autogenerate: Annotated[bool, typer.Option(help="自動生成遷移腳本")] = False):
    typer.secho("Creating new Alembic revision in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.revision(alembic_cfg, message=message, autogenerate=autogenerate, verbose=True)
        typer.secho("Alembic revision created successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error creating detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-stamp-head-verbose", help="將資料庫標記為最新版本並顯示詳細資訊。")
def alembic_stamp_head_verbose_command():
    typer.secho("Stamping database to the latest version in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.stamp(alembic_cfg, "head", verbose=True)
        typer.secho("Database stamped to the latest version successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error stamping detailed database to head: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-history-limit-verbose", help="顯示最近的遷移歷史並顯示詳細資訊。")
def alembic_history_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的歷史記錄數量")]):
    typer.secho(f"Displaying last {limit} Alembic migration history entries in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.history(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited history: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-branches-limit-verbose", help="顯示最近的分支並顯示詳細資訊。")
def alembic_branches_limit_verbose_command(limit: Annotated[int, typer.Option(help="要顯示的分支數量")]):
    typer.secho(f"Displaying last {limit} Alembic branches in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.branches(alembic_cfg, limit=limit, verbose=True)
    except Exception as e:
        typer.secho(f"Error displaying detailed limited branches: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-merge-message-verbose", help="合併多個 head 版本並提供訊息，顯示詳細資訊。")
def alembic_merge_message_verbose_command(revisions: Annotated[str, typer.Option(help="要合併的版本號，用逗號分隔")], message: Annotated[str, typer.Option(help="合併訊息")] = None):
    typer.secho(f"Merging revisions {revisions} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.merge(alembic_cfg, revisions, message=message, verbose=True)
        typer.secho("Revisions merged successfully.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error merging detailed revisions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("alembic-edit-message-verbose", help="編輯特定遷移腳本並提供訊息，顯示詳細資訊。")
def alembic_edit_message_verbose_command(revision: Annotated[str, typer.Option(help="版本號")], message: Annotated[str, typer.Option(help="編輯訊息")] = None):
    typer.secho(f"Editing revision {revision} with message in detail...", fg=typer.colors.BLUE)
    try:
        alembic_cfg = get_alembic_config()
        command.edit(alembic_cfg, revision, message=message, verbose=True)
        typer.secho("Revision opened for editing.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error editing detailed revision: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("generate-report", help="產生並儲存 CSV 格式的帳務報表。")
def generate_report_command(
    output_file: Annotated[str, typer.Option(help="輸出的 CSV 檔案路徑")] = "report.csv",
    month: Annotated[str, typer.Option(help="報表月份，格式為 YYYY-MM (可選)")] = None,
    year: Annotated[int, typer.Option(help="報表年份 (可選)")] = None,
    user: Annotated[str, typer.Option(help="特定使用者名稱 (可選)")] = None
):
    """Generates and saves an accounting report in CSV format."""
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    typer.secho(f"Generating report to {output_file}...", fg=typer.colors.BLUE)
    try:
        report_df = generate_accounting_report(db, month=month, year=year, user_name=user)
        if not report_df.empty:
            report_df.to_csv(output_file, index=False)
            typer.secho(f"Report saved to {output_file}", fg=typer.colors.GREEN)
        else:
            typer.secho("No data found for the specified criteria.", fg=typer.colors.YELLOW)
    except Exception as e:
        typer.secho(f"Error generating report: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("manage-user", help="管理使用者帳戶 (新增、刪除、設定額度)。")
def manage_user_command(
    action: Annotated[str, typer.Argument(help="動作: create, delete, set-quota, list")],
    username: Annotated[str, typer.Option(help="使用者名稱")] = None,
    password: Annotated[str, typer.Option(help="密碼 (僅限 create)")] = None,
    role: Annotated[str, typer.Option(help="角色 (僅限 create): user 或 admin")] = "user",
    cpu_limit: Annotated[float, typer.Option(help="CPU 核心小時額度 (僅限 set-quota)")] = None,
    gpu_limit: Annotated[float, typer.Option(help="GPU 核心小時額度 (僅限 set-quota)")] = None
):
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    if action == "create":
        if not username or not password:
            typer.secho("Username and password are required for creating a user.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            create_user(db, username, password, role)
            typer.secho(f"User '{username}' created with role '{role}'.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Error creating user: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif action == "delete":
        if not username:
            typer.secho("Username is required for deleting a user.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        user_to_delete = get_user(db, username)
        if user_to_delete and delete_user(db, user_to_delete.id):
            typer.secho(f"User '{username}' deleted.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"User '{username}' not found or could not be deleted.", fg=typer.colors.YELLOW)
    elif action == "set-quota":
        if not username or cpu_limit is None or gpu_limit is None:
            typer.secho("Username, CPU limit, and GPU limit are required for setting quota.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        user_for_quota = get_user(db, username)
        if user_for_quota:
            set_user_quota(db, user_for_quota.id, cpu_limit, gpu_limit)
            typer.secho(f"Quota set for user '{username}': CPU={cpu_limit}, GPU={gpu_limit}.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"User '{username}' not found.", fg=typer.colors.YELLOW)
    elif action == "list":
        users = get_all_registered_users(db)
        if users:
            typer.secho("Registered Users:", fg=typer.colors.BLUE)
            for user_data in users:
                typer.echo(f"  - {user_data['username']} (Role: {user_data['role']})")
        else:
            typer.secho("No registered users found.", fg=typer.colors.YELLOW)
    else:
        typer.secho("Invalid action. Use create, delete, set-quota, or list.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("reset-db", help="刪除現有資料庫並重新初始化所有表格。")
def reset_db_command():
    """Deletes the existing database file and re-initializes all tables."""
    db_file = os.getenv("DATABASE_FILE", "./resource_accounting.db")
    if os.path.exists(db_file):
        typer.secho(f"Deleting existing database file: {db_file}...", fg=typer.colors.YELLOW)
        os.remove(db_file)
        typer.secho("Database file deleted.", fg=typer.colors.GREEN)
    
    typer.secho("Re-creating all database tables...", fg=typer.colors.BLUE)
    from database import create_all_tables
    create_all_tables()
    typer.secho("All database tables re-created successfully.", fg=typer.colors.GREEN)

@app.command("manage-wallet", help="管理錢包 (新增、刪除、列出)。")
def manage_wallet_command(
    action: Annotated[str, typer.Argument(help="動作: create, delete, list")],
    name: Annotated[str, typer.Option(help="錢包名稱 (僅限 create, delete)")]=None,
    description: Annotated[str, typer.Option(help="錢包描述 (僅限 create)")]=None,
    wallet_id: Annotated[int, typer.Option(help="錢包ID (僅限 delete)")]=None
):
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    if action == "create":
        if not name:
            typer.secho("Wallet name is required for creating a wallet.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            create_wallet(db, name, description)
            typer.secho(f"Wallet '{name}' created.", fg=typer.colors.GREEN)
        except ValueError as e:
            typer.secho(f"Error creating wallet: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif action == "delete":
        if not wallet_id:
            typer.secho("Wallet ID is required for deleting a wallet.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if delete_wallet(db, wallet_id):
            typer.secho(f"Wallet ID {wallet_id} deleted.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Wallet ID {wallet_id} not found or could not be deleted.", fg=typer.colors.YELLOW)
    elif action == "list":
        wallets = get_all_wallets(db)
        if wallets:
            typer.secho("Current Wallets:", fg=typer.colors.BLUE)
            for w in wallets:
                typer.echo(f"  ID: {w['id']}, Name: {w['name']}, Description: {w['description']}")
        else:
            typer.secho("No wallets found.", fg=typer.colors.YELLOW)
    else:
        typer.secho("Invalid action. Use create, delete, or list.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("manage-group-to-wallet-mapping", help="管理群組到錢包的對應規則 (新增、刪除、列出)。")
def manage_group_to_wallet_mapping_command(
    action: Annotated[str, typer.Argument(help="動作: add, delete, list")],
    source_group: Annotated[str, typer.Option(help="來源群組名稱 (僅限 add)")] = None,
    wallet_name: Annotated[str, typer.Option(help="目標錢包名稱 (僅限 add)")] = None,
    mapping_id: Annotated[int, typer.Option(help="對應規則ID (僅限 delete)")] = None
):
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    if action == "add":
        if not source_group or not wallet_name:
            typer.secho("Source group and wallet name are required for adding a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            add_group_to_wallet_mapping(db, source_group, wallet_name)
            typer.secho(f"Mapping added: Group '{source_group}' -> Wallet '{wallet_name}'.", fg=typer.colors.GREEN)
        except ValueError as e:
            typer.secho(f"Error adding mapping: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif action == "delete":
        if not mapping_id:
            typer.secho("Mapping ID is required for deleting a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if delete_group_to_wallet_mapping(db, mapping_id):
            typer.secho(f"Mapping ID {mapping_id} deleted.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Mapping ID {mapping_id} not found or could not be deleted.", fg=typer.colors.YELLOW)
    elif action == "list":
        mappings = get_all_group_to_wallet_mappings(db)
        if mappings:
            typer.secho("Current Group to Wallet Mappings:", fg=typer.colors.BLUE)
            for m in mappings:
                typer.echo(f"  ID: {m['id']}, Group: {m['source_group']} -> Wallet: {m['wallet_name']}")
        else:
            typer.secho("No group to wallet mappings found.", fg=typer.colors.YELLOW)
    else:
        typer.secho("Invalid action. Use add, delete, or list.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("manage-user-to-wallet-mapping", help="管理使用者到錢包的對應規則 (新增、刪除、列出)。")
def manage_user_to_wallet_mapping_command(
    action: Annotated[str, typer.Argument(help="動作: add, delete, list")],
    username: Annotated[str, typer.Option(help="來源使用者名稱 (僅限 add)")] = None,
    wallet_name: Annotated[str, typer.Option(help="目標錢包名稱 (僅限 add)")] = None,
    mapping_id: Annotated[int, typer.Option(help="對應規則ID (僅限 delete)")] = None
):
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    if action == "add":
        if not username or not wallet_name:
            typer.secho("Username and wallet name are required for adding a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            add_user_to_wallet_mapping(db, username, wallet_name)
            typer.secho(f"Mapping added: User '{username}' -> Wallet '{wallet_name}'.", fg=typer.colors.GREEN)
        except ValueError as e:
            typer.secho(f"Error adding mapping: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif action == "delete":
        if not mapping_id:
            typer.secho("Mapping ID is required for deleting a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if delete_user_to_wallet_mapping(db, mapping_id):
            typer.secho(f"Mapping ID {mapping_id} deleted.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Mapping ID {mapping_id} not found or could not be deleted.", fg=typer.colors.YELLOW)
    elif action == "list":
        mappings = get_all_user_to_wallet_mappings(db)
        if mappings:
            typer.secho("Current User to Wallet Mappings:", fg=typer.colors.BLUE)
            for m in mappings:
                typer.echo(f"  ID: {m['id']}, User: {m['username']} -> Wallet: {m['wallet_name']}")
        else:
            typer.secho("No user to wallet mappings found.", fg=typer.colors.YELLOW)
    else:
        typer.secho("Invalid action. Use add, delete, or list.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command("manage-mapping", help="管理群組對應規則 (將群組用量歸屬到特定帳戶)。")
def manage_mapping_command(
    action: Annotated[str, typer.Argument(help="動作: add, delete, list")],
    source_group: Annotated[str, typer.Option(help="來源群組名稱 (僅限 add, delete)")] = None,
    target_username: Annotated[str, typer.Option(help="目標使用者名稱 (僅限 add)")] = None,
    mapping_id: Annotated[int, typer.Option(help="對應規則ID (僅限 delete)")] = None
):
    db = next(get_db())
    authenticate_admin_cli(db) # Admin authentication required

    if action == "add":
        if not source_group or not target_username:
            typer.secho("Source group and target username are required for adding a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        try:
            add_group_mapping(db, source_group, target_username)
            typer.secho(f"Mapping added: Group '{source_group}' -> User '{target_username}'.", fg=typer.colors.GREEN)
        except ValueError as e:
            typer.secho(f"Error adding mapping: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif action == "delete":
        if not mapping_id:
            typer.secho("Mapping ID is required for deleting a mapping.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        if delete_group_mapping(db, mapping_id):
            typer.secho(f"Mapping ID {mapping_id} deleted.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"Mapping ID {mapping_id} not found or could not be deleted.", fg=typer.colors.YELLOW)
    elif action == "list":
        mappings = get_all_group_mappings(db)
        if mappings:
            typer.secho("Current Group Mappings:", fg=typer.colors.BLUE)
            for m in mappings:
                typer.echo(f"  ID: {m['id']}, Group: {m['source_group']} -> User: {m['target_username']}")
        else:
            typer.secho("No group mappings found.", fg=typer.colors.YELLOW)
    else:
        typer.secho("Invalid action. Use add, delete, or list.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()