"""Add performance indexes for query optimization

Revision ID: c5892216
Revises: 6a3e94a3daa1
Create Date: 2025-01-06 15:07:48.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5892216'
down_revision: Union[str, None] = '6a3e94a3daa1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes to optimize query speed."""
    # Note: These indexes may take some time to create on large databases
    # It's recommended to run this migration during maintenance windows
    
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        # Add single column indexes for date fields
        batch_op.create_index('ix_jobs_start_time', ['start_time'], unique=False)
        batch_op.create_index('ix_jobs_queue_time', ['queue_time'], unique=False)
        
        # Composite indexes for common query patterns
        # Index for time range queries with resource type
        batch_op.create_index('ix_jobs_start_time_resource_type', 
                             ['start_time', 'resource_type'], unique=False)
        
        # Index for time range queries with wallet
        batch_op.create_index('ix_jobs_start_time_wallet_name', 
                             ['start_time', 'wallet_name'], unique=False)
        
        # Index for time range queries with user
        batch_op.create_index('ix_jobs_start_time_user_name', 
                             ['start_time', 'user_name'], unique=False)
        
        # Index for multi-dimensional queries
        batch_op.create_index('ix_jobs_start_time_user_group_resource_type', 
                             ['start_time', 'user_group', 'resource_type'], unique=False)
        
        # Covering index for aggregation queries
        batch_op.create_index('ix_jobs_start_time_resource_type_metrics', 
                             ['start_time', 'resource_type', 'run_time_seconds', 'nodes', 'cores'], 
                             unique=False)
        
        # Index for queue time queries
        batch_op.create_index('ix_jobs_queue_time_start_time', 
                             ['queue_time', 'start_time'], unique=False)


def downgrade() -> None:
    """Remove performance indexes."""
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_queue_time_start_time')
        batch_op.drop_index('ix_jobs_start_time_resource_type_metrics')
        batch_op.drop_index('ix_jobs_start_time_user_group_resource_type')
        batch_op.drop_index('ix_jobs_start_time_user_name')
        batch_op.drop_index('ix_jobs_start_time_wallet_name')
        batch_op.drop_index('ix_jobs_start_time_resource_type')
        batch_op.drop_index('ix_jobs_queue_time')
        batch_op.drop_index('ix_jobs_start_time')


