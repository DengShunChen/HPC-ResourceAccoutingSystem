import os
import redis
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case, Integer, String
from sqlalchemy.sql import expression # Import expression module
import pandas as pd
import json
from functools import wraps
from datetime import datetime, timedelta, date

from database import Job, User, Quota, GroupMapping

# --- Redis Cache Connection ---
# In a real app, Redis connection details would also come from env vars
# For simplicity, we'll use default localhost for now
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)

# --- Cache Decorator ---
def json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def cache_results(ttl_seconds=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key based on function name and arguments
            processed_args = [str(a) if isinstance(a, (datetime, date)) else a for a in args]
            processed_kwargs = {k: (str(v) if isinstance(v, (datetime, date)) else v) for k, v in kwargs.items()}

            key_parts = [func.__name__] + [str(a) for a in processed_args] + [f"{k}={v}" for k, v in sorted(processed_kwargs.items())]
            cache_key = ":".join(key_parts)

            try:
                cached_data = redis_client.get(cache_key)
                if cached_data:
                    # print(f"Cache HIT for key: {cache_key}")
                    loaded_data = json.loads(cached_data)
                    # Check if the result is a string that looks like a date and convert it back
                    if isinstance(loaded_data, str):
                        try:
                            return date.fromisoformat(loaded_data)
                        except (ValueError, TypeError):
                            pass # Not a date string, return as is
                    return loaded_data
            except redis.exceptions.RedisError as e:
                print(f"Redis error on GET: {e}")
                # Fall through to execute the function

            # print(f"Cache MISS for key: {cache_key}")
            result = func(*args, **kwargs)

            # Serialize and cache the result
            try:
                if isinstance(result, pd.DataFrame):
                    redis_client.setex(cache_key, ttl_seconds, result.to_json())
                else:
                    redis_client.setex(cache_key, ttl_seconds, json.dumps(result, default=json_serializer))
            except (TypeError, redis.exceptions.RedisError) as e:
                print(f"Could not serialize result for caching: {e}")

            return result
        return wrapper
    return decorator

# --- Helper Functions ---
def _get_resource_seconds_expression():
    """
    Returns the SQLAlchemy CASE expression for calculating resource-seconds.
    It calculates node-seconds for CPU and core-seconds for GPU.
    """
    return case(
        (Job.resource_type == 'CPU', Job.run_time_seconds * Job.nodes),
        (Job.resource_type == 'GPU', Job.run_time_seconds * Job.cores),
        else_=0
    )

# --- Query Functions ---

@cache_results(ttl_seconds=60)
def get_kpi_data(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, queue: str = None, wallet_name: str = None):
    """Calculates key performance indicators (KPIs)."""
    base_query = db.query(Job).filter(Job.start_time >= start_date, Job.start_time <= (end_date + timedelta(days=1)))

    # Apply filters
    if user_name and user_name != "(全部)":
        base_query = base_query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        base_query = base_query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        base_query = base_query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        base_query = base_query.filter(Job.wallet_name == wallet_name)

    # Perform aggregations
    # CPU aggregation
    cpu_agg_query = base_query.filter(Job.resource_type == 'CPU').with_entities(
        func.sum(Job.run_time_seconds * Job.nodes).label('total_node_seconds'),
        func.count(Job.id).label('total_jobs'),
        func.avg(Job.run_time_seconds).label('avg_run_time_seconds')
    )
    # GPU aggregation
    gpu_agg_query = base_query.filter(Job.resource_type == 'GPU').with_entities(
        func.sum(Job.run_time_seconds * Job.cores).label('total_core_seconds'),
        func.count(Job.id).label('total_jobs'),
        func.avg(Job.run_time_seconds).label('avg_run_time_seconds')
    )

    overall_agg_query = base_query.with_entities(
        func.count(Job.id).label('total_jobs'),
        func.avg(Job.run_time_seconds).label('avg_run_time'),
        func.count(func.distinct(Job.user_name)).label('unique_users'),
        func.avg((func.julianday(Job.start_time) - func.julianday(Job.queue_time)) * 86400).label('avg_wait_time'),
        func.sum(case((Job.job_status == 'COMPLETED', 1), else_=0)).label('completed_jobs')
    )

    cpu_results = cpu_agg_query.first()
    gpu_results = gpu_agg_query.first()
    overall_results = overall_agg_query.first()

    kpis = {
        'CPU': {'total_node_hours': 0, 'total_jobs': 0, 'avg_run_time_seconds': 0},
        'GPU': {'total_core_hours': 0, 'total_jobs': 0, 'avg_run_time_seconds': 0},
        'overall_total_jobs': overall_results.total_jobs if overall_results else 0,
        'overall_avg_run_time': (overall_results.avg_run_time or 0) if overall_results else 0,
        'unique_users': overall_results.unique_users if overall_results else 0,
        'avg_wait_time': (overall_results.avg_wait_time or 0) if overall_results else 0,
        'success_rate': (overall_results.completed_jobs / overall_results.total_jobs * 100) if (overall_results and overall_results.total_jobs > 0 and overall_results.completed_jobs is not None) else 0,
    }

    if cpu_results and cpu_results.total_node_seconds is not None:
        kpis['CPU']['total_node_hours'] = cpu_results.total_node_seconds / 3600
        kpis['CPU']['total_jobs'] = cpu_results.total_jobs
        kpis['CPU']['avg_run_time_seconds'] = cpu_results.avg_run_time_seconds

    if gpu_results and gpu_results.total_core_seconds is not None:
        kpis['GPU']['total_core_hours'] = gpu_results.total_core_seconds / 3600
        kpis['GPU']['total_jobs'] = gpu_results.total_jobs
        kpis['GPU']['avg_run_time_seconds'] = gpu_results.avg_run_time_seconds

    return kpis

@cache_results(ttl_seconds=300)
def get_usage_over_time(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, queue: str = None, wallet_name: str = None, time_granularity: str = 'daily'):
    """Gets resource usage aggregated by day, month, quarter, or year."""
    if time_granularity == 'daily':
        date_format_str = '%Y-%m-%d'
        date_label = func.strftime(date_format_str, Job.start_time).label('date')
    elif time_granularity == 'monthly':
        date_format_str = '%Y-%m'
        date_label = func.strftime(date_format_str, Job.start_time).label('date')
    elif time_granularity == 'quarterly':
        year_str = func.strftime('%Y', Job.start_time)
        month_num = extract('month', Job.start_time)
        quarter_num = case(
            (month_num.between(1, 3), expression.literal('Q1')),
            (month_num.between(4, 6), expression.literal('Q2')),
            (month_num.between(7, 9), expression.literal('Q3')),
            (month_num.between(10, 12), expression.literal('Q4')),
            else_=expression.literal('')
        )
        date_label = (year_str + expression.literal('-') + quarter_num).label('date')
    elif time_granularity == 'yearly':
        date_format_str = '%Y'
        date_label = func.strftime(date_format_str, Job.start_time).label('date')
    else: # Default to daily
        date_format_str = '%Y-%m-%d'
        date_label = func.strftime(date_format_str, Job.start_time).label('date')

    resource_seconds_expr = _get_resource_seconds_expression()
    query = db.query(
        date_label,
        Job.resource_type,
        func.sum(resource_seconds_expr).label('daily_resource_seconds')
    ).group_by(date_label, Job.resource_type).order_by(date_label)

    # Apply filters
    query = query.filter(Job.start_time >= start_date, Job.start_time <= (end_date + timedelta(days=1)))
    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    results = query.all()
    return [{
        'date': r.date,
        'resource_type': r.resource_type,
        'daily_node_seconds': r.daily_resource_seconds or 0
    } for r in results]

@cache_results(ttl_seconds=300)
def get_filtered_jobs(db: Session, page: int = 1, page_size: int = 20,
                      start_date: date = None, end_date: date = None,
                      user_name: str = None, user_group: str = None,
                      queue: str = None, resource_type: str = None, wallet_name: str = None):
    """Gets a paginated list of jobs with filters."""
    query = db.query(Job)

    # Apply filters
    if start_date:
        query = query.filter(Job.start_time >= start_date)
    if end_date:
        query = query.filter(Job.start_time <= (end_date + timedelta(days=1)))
    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if resource_type and resource_type != "(全部)":
        query = query.filter(Job.resource_type == resource_type)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    total_items = query.count()
    jobs = query.offset((page - 1) * page_size).limit(page_size).all()

    # Convert Job objects to dictionaries for JSON serialization
    jobs_data = []
    for job in jobs:
        job_dict = {c.name: getattr(job, c.name) for c in job.__table__.columns}
        # Convert datetime objects to string for JSON compatibility
        for k, v in job_dict.items():
            if isinstance(v, datetime):
                job_dict[k] = v.isoformat()
        jobs_data.append(job_dict)

    return {"total_items": total_items, "jobs": jobs_data}

@cache_results(ttl_seconds=3600) # Cache for 1 hour
def get_all_users(db: Session, user_group: str = None, queue: str = None, wallet_name: str = None):
    """Gets a list of all unique user names from jobs and users table."""
    job_query = db.query(Job.user_name).distinct()
    if user_group and user_group != "(全部)":
        job_query = job_query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        job_query = job_query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        job_query = job_query.filter(Job.wallet_name == wallet_name)
    job_users = job_query.all()

    registered_users = db.query(User.username).distinct().all()
    all_users = sorted(list(set([u[0] for u in job_users] + [u[0] for u in registered_users])))
    return all_users

@cache_results(ttl_seconds=3600) # Cache for 1 hour
def get_all_groups(db: Session, user_name: str = None, queue: str = None, wallet_name: str = None):
    """Gets a list of all unique user groups from jobs table."""
    query = db.query(Job.user_group).distinct()
    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)
    groups = query.all()
    return sorted([g[0] for g in groups])

@cache_results(ttl_seconds=3600) # Cache for 1 hour
def get_all_queues(db: Session, wallet_name: str = None):
    """Gets a list of all unique queues from jobs table."""
    query = db.query(Job.queue).distinct()
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)
    queues = query.all()
    return sorted([q[0] for q in queues])


# --- Admin Panel Queries ---

def get_all_registered_users(db: Session):
    """Gets all registered users with their roles."""
    users = db.query(User).all()
    return [{'id': u.id, 'username': u.username, 'role': u.role} for u in users]

def get_user_quota(db: Session, user_id: int):
    """Gets quota for a specific user."""
    return db.query(Quota).filter(Quota.user_id == user_id).first()

def set_user_quota(db: Session, user_id: int, cpu_limit: float, gpu_limit: float, period: str = "monthly"):
    """Sets or updates quota for a user."""
    quota = db.query(Quota).filter(Quota.user_id == user_id, Quota.period == period).first()
    if quota:
        quota.cpu_core_hours_limit = cpu_limit
        quota.gpu_core_hours_limit = gpu_limit
    else:
        quota = Quota(user_id=user_id, cpu_core_hours_limit=cpu_limit, gpu_core_hours_limit=gpu_limit, period=period)
        db.add(quota)
    db.commit()
    db.refresh(quota)
    return quota

def delete_user(db: Session, user_id: int):
    """Deletes a user and their associated quotas and mappings."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Delete associated quotas
        db.query(Quota).filter(Quota.user_id == user_id).delete()
        # Delete associated group mappings
        db.query(GroupMapping).filter(GroupMapping.target_user_id == user_id).delete()
        db.delete(user)
        db.commit()
        return True
    return False

def get_all_group_mappings(db: Session):
    """Gets all group mappings with target usernames."""
    mappings = db.query(GroupMapping, User.username).join(User, GroupMapping.target_user_id == User.id).all()
    return [{'id': m.GroupMapping.id, 'source_group': m.GroupMapping.source_group, 'target_username': m.username} for m in mappings]

def add_group_mapping(db: Session, source_group: str, target_username: str):
    """Adds a new group mapping."""
    target_user = db.query(User).filter(User.username == target_username).first()
    if not target_user:
        raise ValueError(f"Target user '{target_username}' not found.")

    existing_mapping = db.query(GroupMapping).filter(GroupMapping.source_group == source_group).first()
    if existing_mapping:
        raise ValueError(f"Mapping for group '{source_group}' already exists.")

    new_mapping = GroupMapping(source_group=source_group, target_user_id=target_user.id)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping

def delete_group_mapping(db: Session, mapping_id: int):
    """Deletes a group mapping by ID."""
    mapping = db.query(GroupMapping).filter(GroupMapping.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return True
    return False


# --- Group to Group Mappings ---
from database import GroupToGroupMapping

@cache_results(ttl_seconds=3600)
def get_all_group_to_group_mappings(db: Session):
    """Gets all group-to-group mappings."""
    mappings = db.query(GroupToGroupMapping).all()
    return [{'id': m.id, 'source_group': m.source_group, 'target_group': m.target_group} for m in mappings]

def add_group_to_group_mapping(db: Session, source_group: str, target_group: str):
    """Adds a new group-to-group mapping."""
    existing_mapping = db.query(GroupToGroupMapping).filter(GroupToGroupMapping.source_group == source_group).first()
    if existing_mapping:
        raise ValueError(f"Mapping for source group '{source_group}' already exists.")

    new_mapping = GroupToGroupMapping(source_group=source_group, target_group=target_group)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping

def delete_group_to_group_mapping(db: Session, mapping_id: int):
    """Deletes a group-to-group mapping by ID."""
    mapping = db.query(GroupToGroupMapping).filter(GroupToGroupMapping.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return True
    return False


# --- Report Generation (Placeholder) ---
from database import GroupToGroupMapping, Wallet, GroupToWalletMapping, UserToWalletMapping

@cache_results(ttl_seconds=3600)
def get_all_group_to_group_mappings(db: Session):
    """Gets all group-to-group mappings."""
    mappings = db.query(GroupToGroupMapping).all()
    return [{'id': m.id, 'source_group': m.source_group, 'target_group': m.target_group} for m in mappings]

def add_group_to_group_mapping(db: Session, source_group: str, target_group: str):
    """Adds a new group-to-group mapping."""
    existing_mapping = db.query(GroupToGroupMapping).filter(GroupToGroupMapping.source_group == source_group).first()
    if existing_mapping:
        raise ValueError(f"Mapping for source group '{source_group}' already exists.")

    new_mapping = GroupToGroupMapping(source_group=source_group, target_group=target_group)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping

def delete_group_to_group_mapping(db: Session, mapping_id: int):
    """Deletes a group-to-group mapping by ID."""
    mapping = db.query(GroupToGroupMapping).filter(GroupToGroupMapping.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return True
    return False


# --- Wallet Management ---

@cache_results(ttl_seconds=3600)
def get_all_wallets(db: Session):
    """Gets all registered wallets."""
    wallets = db.query(Wallet).all()
    return [{'id': w.id, 'name': w.name, 'description': w.description} for w in wallets]

def get_wallet_by_name(db: Session, name: str):
    """Gets a wallet by its name."""
    return db.query(Wallet).filter(Wallet.name == name).first()

def get_wallet_by_id(db: Session, wallet_id: int):
    """Gets a wallet by its ID."""
    return db.query(Wallet).filter(Wallet.id == wallet_id).first()

def create_wallet(db: Session, name: str, description: str = None):
    """Creates a new wallet."""
    existing_wallet = get_wallet_by_name(db, name)
    if existing_wallet:
        raise ValueError(f"Wallet '{name}' already exists.")
    new_wallet = Wallet(name=name, description=description)
    db.add(new_wallet)
    db.commit()
    db.refresh(new_wallet)
    return new_wallet

def delete_wallet(db: Session, wallet_id: int):
    """Deletes a wallet by ID and associated mappings."""
    wallet = get_wallet_by_id(db, wallet_id)
    if wallet:
        # Delete associated group-to-wallet mappings
        db.query(GroupToWalletMapping).filter(GroupToWalletMapping.wallet_id == wallet_id).delete()
        # Delete associated user-to-wallet mappings
        db.query(UserToWalletMapping).filter(UserToWalletMapping.wallet_id == wallet_id).delete()
        db.delete(wallet)
        db.commit()
        return True
    return False

def update_wallet(db: Session, wallet_id: int, new_name: str = None, new_description: str = None):
    """Updates an existing wallet's name and/or description."""
    wallet = get_wallet_by_id(db, wallet_id)
    if not wallet:
        raise ValueError(f"Wallet with ID {wallet_id} not found.")

    if new_name:
        # Check if new_name already exists for another wallet
        existing_wallet_with_name = get_wallet_by_name(db, new_name)
        if existing_wallet_with_name and existing_wallet_with_name.id != wallet_id:
            raise ValueError(f"Wallet with name '{new_name}' already exists.")
        wallet.name = new_name

    if new_description is not None:
        wallet.description = new_description

    db.commit()
    db.refresh(wallet)
    return wallet


# --- Group to Wallet Mappings ---

@cache_results(ttl_seconds=3600)
def get_all_group_to_wallet_mappings(db: Session):
    """Gets all group-to-wallet mappings with wallet names."""
    mappings = db.query(GroupToWalletMapping, Wallet.name).join(Wallet, GroupToWalletMapping.wallet_id == Wallet.id).all()
    return [{'id': m.GroupToWalletMapping.id, 'source_group': m.GroupToWalletMapping.source_group, 'wallet_name': m.name} for m in mappings]

def add_group_to_wallet_mapping(db: Session, source_group: str, wallet_name: str):
    """Adds a new group-to-wallet mapping."""
    wallet = get_wallet_by_name(db, wallet_name)
    if not wallet:
        raise ValueError(f"Wallet '{wallet_name}' not found.")

    existing_mapping = db.query(GroupToWalletMapping).filter(GroupToWalletMapping.source_group == source_group).first()
    if existing_mapping:
        raise ValueError(f"Mapping for source group '{source_group}' already exists.")

    new_mapping = GroupToWalletMapping(source_group=source_group, wallet_id=wallet.id)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping

def delete_group_to_wallet_mapping(db: Session, mapping_id: int):
    """Deletes a group-to-wallet mapping by ID."""
    mapping = db.query(GroupToWalletMapping).filter(GroupToWalletMapping.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return True
    return False


# --- User to Wallet Mappings ---

@cache_results(ttl_seconds=3600)
def get_all_user_to_wallet_mappings(db: Session):
    """Gets all user-to-wallet mappings with wallet names and usernames."""
    mappings = db.query(UserToWalletMapping, User.username, Wallet.name).join(User, UserToWalletMapping.user_id == User.id).join(Wallet, UserToWalletMapping.wallet_id == Wallet.id).all()
    return [{'id': m.UserToWalletMapping.id, 'username': m.username, 'wallet_name': m.name} for m in mappings]

def add_user_to_wallet_mapping(db: Session, username: str, wallet_name: str):
    """Adds a new user-to-wallet mapping."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise ValueError(f"User '{username}' not found.")
    wallet = get_wallet_by_name(db, wallet_name)
    if not wallet:
        raise ValueError(f"Wallet '{wallet_name}' not found.")

    existing_mapping = db.query(UserToWalletMapping).filter(UserToWalletMapping.user_id == user.id).first()
    if existing_mapping:
        raise ValueError(f"Mapping for user '{username}' already exists.")

    new_mapping = UserToWalletMapping(user_id=user.id, wallet_id=wallet.id)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)
    return new_mapping

def delete_user_to_wallet_mapping(db: Session, mapping_id: int):
    """Deletes a user-to-wallet mapping by ID."""
    mapping = db.query(UserToWalletMapping).filter(UserToWalletMapping.id == mapping_id).first()
    if mapping:
        db.delete(mapping)
        db.commit()
        return True
    return False


# --- Report Generation (Placeholder) ---
def generate_accounting_report(db: Session, month: str = None, year: int = None, user_name: str = None, wallet_name: str = None):
    """Generates an accounting report for a given month/year/user."""
    # This is a simplified example. Real reports would involve more complex aggregations.
    query = db.query(Job)
    if year:
        query = query.filter(extract('year', Job.start_time) == year)
    if month:
        # Assuming month is 'YYYY-MM'
        query = query.filter(func.strftime('%Y-%m', Job.start_time) == month)
    if user_name:
        query = query.filter(Job.user_name == user_name)
    if wallet_name:
        query = query.filter(Job.wallet_name == wallet_name)

    report_data = pd.read_sql(query.statement, db.bind)
    return report_data

@cache_results(ttl_seconds=300)
def get_top_users_by_core_hours(db: Session, start_date: date, end_date: date, user_group: str = None, queue: str = None, wallet_name: str = None, limit: int = 5):
    """Gets top users by total resource-hours (node-hours for CPU, core-hours for GPU)."""
    resource_seconds_expr = _get_resource_seconds_expression()
    query = db.query(
        Job.user_name,
        func.sum(resource_seconds_expr).label('total_resource_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)
    query = query.group_by(Job.user_name).order_by(func.sum(resource_seconds_expr).desc()).limit(limit)

    results = query.all()
    return [{'user_name': r.user_name, 'core_hours': (r.total_resource_seconds or 0) / 3600} for r in results]

@cache_results(ttl_seconds=300)
def get_top_groups_by_core_hours(db: Session, start_date: date, end_date: date, user_name: str = None, queue: str = None, wallet_name: str = None, limit: int = 5):
    """Gets top groups by total resource-hours (node-hours for CPU, core-hours for GPU)."""
    resource_seconds_expr = _get_resource_seconds_expression()
    query = db.query(
        Job.user_group,
        func.sum(resource_seconds_expr).label('total_resource_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )
    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)
    query = query.group_by(Job.user_group).order_by(func.sum(resource_seconds_expr).desc()).limit(limit)

    results = query.all()
    return [{'user_group': r.user_group, 'core_hours': (r.total_resource_seconds or 0) / 3600} for r in results]

@cache_results(ttl_seconds=300)
def get_top_wallets_by_core_hours(db: Session, start_date: date, end_date: date, limit: int = 5):
    """Gets top wallets by total resource-hours (node-hours for CPU, core-hours for GPU)."""
    resource_seconds_expr = _get_resource_seconds_expression()
    query = db.query(
        Job.wallet_name,
        func.sum(resource_seconds_expr).label('total_resource_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    ).group_by(Job.wallet_name).order_by(func.sum(resource_seconds_expr).desc()).limit(limit)

    results = query.all()
    return [{'wallet_name': r.wallet_name, 'core_hours': (r.total_resource_seconds or 0) / 3600} for r in results]

@cache_results(ttl_seconds=300)
def get_job_status_distribution(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, queue: str = None, wallet_name: str = None):
    """Gets the distribution of job statuses."""
    query = db.query(
        Job.job_status,
        func.count(Job.id).label('job_count')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )

    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    query = query.group_by(Job.job_status)

    results = query.all()
    return [{'job_status': r.job_status, 'job_count': r.job_count} for r in results]

@cache_results(ttl_seconds=300)
def get_usage_by_queue(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, wallet_name: str = None):
    """Gets the usage distribution by queue, in resource-hours."""
    resource_seconds_expr = _get_resource_seconds_expression()
    query = db.query(
        Job.queue,
        func.sum(resource_seconds_expr).label('total_resource_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )

    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    query = query.group_by(Job.queue).order_by(func.sum(resource_seconds_expr).desc())

    results = query.all()
    return [{'queue': r.queue, 'core_hours': (r.total_resource_seconds or 0) / 3600} for r in results]

@cache_results(ttl_seconds=300)
def get_average_job_runtime_by_queue(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, wallet_name: str = None):
    """Gets the average job runtime by queue."""
    query = db.query(
        Job.queue,
        func.avg(Job.run_time_seconds).label('avg_runtime_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )

    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    query = query.group_by(Job.queue).order_by(func.avg(Job.run_time_seconds).desc())

    results = query.all()
    return [{'queue': r.queue, 'avg_runtime_seconds': r.avg_runtime_seconds or 0} for r in results]

@cache_results(ttl_seconds=300)
def get_average_wait_time_by_queue(db: Session, start_date: date, end_date: date):
    """Gets the average job wait time by queue."""
    query = db.query(
        Job.queue,
        func.avg((func.julianday(Job.start_time) - func.julianday(Job.queue_time)) * 86400).label('avg_wait_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    ).group_by(Job.queue).order_by(func.avg((func.julianday(Job.start_time) - func.julianday(Job.queue_time)) * 86400).desc())

    results = query.all()
    return [{'queue': r.queue, 'avg_wait_seconds': r.avg_wait_seconds or 0} for r in results]

@cache_results(ttl_seconds=300)
def get_peak_usage_heatmap(db: Session, start_date: date, end_date: date, user_name: str = None, user_group: str = None, queue: str = None, wallet_name: str = None):
    """Gets data for peak usage heatmap (hour vs. day of week)."""
    query = db.query(
        func.strftime('%w', Job.start_time).label('day_of_week'), # Sunday=0, Monday=1, etc.
        extract('hour', Job.start_time).label('hour_of_day'),
        func.count(Job.id).label('job_count')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    )

    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    query = query.group_by('day_of_week', 'hour_of_day')

    results = query.all()
    return [{'day_of_week': r.day_of_week, 'hour_of_day': r.hour_of_day, 'job_count': r.job_count} for r in results]

@cache_results(ttl_seconds=3600) # Cache for an hour
def get_first_job_date(db: Session) -> date:
    """Gets the earliest job start date from the database."""
    first_job_date = db.query(func.min(Job.start_time)).scalar()
    return first_job_date if first_job_date else date.today()

@cache_results(ttl_seconds=3600) # Cache for an hour
def get_last_job_date(db: Session) -> date:
    """Gets the latest job start date from the database."""
    last_job_date = db.query(func.max(Job.start_time)).scalar()
    return last_job_date if last_job_date else date.today()

@cache_results(ttl_seconds=300)
def get_failure_rate_by_group(db: Session, start_date: date, end_date: date, limit: int = 10):
    """Calculates the job failure rate per group."""
    failed_statuses = ['FAILED', 'TIMEOUT', 'USER_CANCELED']
    query = db.query(
        Job.user_group,
        func.count(Job.id).label('total_jobs'),
        func.sum(case((Job.job_status.in_(failed_statuses), 1), else_=0)).label('failed_jobs')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    ).group_by(Job.user_group)

    results = query.all()

    failure_rates = []
    for r in results:
        if r.total_jobs > 0:
            rate = (r.failed_jobs / r.total_jobs) * 100
            failure_rates.append({'group': r.user_group, 'failure_rate': rate, 'total_jobs': r.total_jobs})

    # Sort by failure rate and return top N
    sorted_rates = sorted(failure_rates, key=lambda x: x['failure_rate'], reverse=True)
    return sorted_rates[:limit]

@cache_results(ttl_seconds=300)
def get_failure_rate_by_user(db: Session, start_date: date, end_date: date, limit: int = 10):
    """Calculates the job failure rate per user."""
    failed_statuses = ['FAILED', 'TIMEOUT', 'USER_CANCELED']
    query = db.query(
        Job.user_name,
        func.count(Job.id).label('total_jobs'),
        func.sum(case((Job.job_status.in_(failed_statuses), 1), else_=0)).label('failed_jobs')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1))
    ).group_by(Job.user_name)

    results = query.all()

    failure_rates = []
    for r in results:
        if r.total_jobs > 0:
            rate = (r.failed_jobs / r.total_jobs) * 100
            failure_rates.append({'user': r.user_name, 'failure_rate': rate, 'total_jobs': r.total_jobs})

    # Sort by failure rate and return top N
    sorted_rates = sorted(failure_rates, key=lambda x: x['failure_rate'], reverse=True)
    return sorted_rates[:limit]

@cache_results(ttl_seconds=300)
def get_wallet_usage_by_resource_type(db: Session, start_date: date, end_date: date, resource_type: str, user_name: str = None, user_group: str = None, queue: str = None, wallet_name: str = None):
    """Gets wallet usage by total resource-hours for a specific resource type."""
    if resource_type == 'GPU':
        sum_expr = func.sum(Job.run_time_seconds * Job.cores)
    else: # Default to CPU logic (node-hours)
        sum_expr = func.sum(Job.run_time_seconds * Job.nodes)

    query = db.query(
        Job.wallet_name,
        sum_expr.label('total_resource_seconds')
    ).filter(
        Job.start_time >= start_date,
        Job.start_time <= (end_date + timedelta(days=1)),
        Job.resource_type == resource_type
    )

    if user_name and user_name != "(全部)":
        query = query.filter(Job.user_name == user_name)
    if user_group and user_group != "(全部)":
        query = query.filter(Job.user_group == user_group)
    if queue and queue != "(全部)":
        query = query.filter(Job.queue == queue)
    if wallet_name and wallet_name != "(全部)":
        query = query.filter(Job.wallet_name == wallet_name)

    query = query.group_by(Job.wallet_name).order_by(sum_expr.desc())

    results = query.all()
    return [{'wallet_name': r.wallet_name, 'core_hours': (r.total_resource_seconds or 0) / 3600} for r in results]

@cache_results(ttl_seconds=60)
def get_active_resources(db: Session):
    """
    Gets the number of currently active CPU nodes and GPU cores.
    A resource is considered active if its job is currently running.
    """
    now = datetime.utcnow()

    # For SQLite, we need to use the datetime function to add seconds.
    job_end_time = func.datetime(Job.start_time, '+' + func.cast(Job.run_time_seconds, String) + ' seconds')

    # Query for jobs that are currently running (start_time <= now < end_time)
    active_jobs_query = db.query(Job).filter(
        Job.start_time <= now,
        job_end_time > now
    )

    active_cpu_nodes = active_jobs_query.filter(Job.resource_type == 'CPU').with_entities(func.sum(Job.nodes)).scalar()
    active_gpu_cores = active_jobs_query.filter(Job.resource_type == 'GPU').with_entities(func.sum(Job.cores)).scalar()

    return {
        "active_cpu_nodes": active_cpu_nodes or 0,
        "active_gpu_cores": active_gpu_cores or 0
    }

