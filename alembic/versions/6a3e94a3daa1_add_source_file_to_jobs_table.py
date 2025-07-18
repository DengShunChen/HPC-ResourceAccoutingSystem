"""Add source_file to jobs table

Revision ID: 6a3e94a3daa1
Revises: 68da61661014
Create Date: 2025-07-18 14:25:51.994650

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a3e94a3daa1'
down_revision: Union[str, None] = '68da61661014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('group_mappings', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_group_mappings_target_user_id', 'users', ['target_user_id'], ['id'])

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_file', sa.String(), nullable=True))
        batch_op.create_index(batch_op.f('ix_jobs_source_file'), ['source_file'], unique=False)

    with op.batch_alter_table('quotas', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_quotas_user_id', 'users', ['user_id'], ['id'])

    with op.batch_alter_table('user_to_wallet_mappings', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_user_to_wallet_mappings_user_id', 'users', ['user_id'], ['id'])

def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user_to_wallet_mappings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_to_wallet_mappings_user_id', type_='foreignkey')

    with op.batch_alter_table('quotas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_quotas_user_id', type_='foreignkey')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_source_file'))
        batch_op.drop_column('source_file')

    with op.batch_alter_table('group_mappings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_group_mappings_target_user_id', type_='foreignkey')
