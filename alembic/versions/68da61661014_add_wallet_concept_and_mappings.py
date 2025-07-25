"""Add wallet concept and mappings

Revision ID: 68da61661014
Revises: aeee40038c58
Create Date: 2025-07-16 12:02:10.504191

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68da61661014'
down_revision: Union[str, None] = 'aeee40038c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('jobs', sa.Column('wallet_name', sa.String(), nullable=True))
    op.create_index(op.f('ix_jobs_wallet_name'), 'jobs', ['wallet_name'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_jobs_wallet_name'), table_name='jobs')
    op.drop_column('jobs', 'wallet_name')
    op.drop_index(op.f('ix_user_to_wallet_mappings_user_id'), table_name='user_to_wallet_mappings')
    op.drop_index(op.f('ix_user_to_wallet_mappings_id'), table_name='user_to_wallet_mappings')
    op.drop_table('user_to_wallet_mappings')
    op.drop_index(op.f('ix_group_to_wallet_mappings_source_group'), table_name='group_to_wallet_mappings')
    op.drop_index(op.f('ix_group_to_wallet_mappings_id'), table_name='group_to_wallet_mappings')
    op.drop_table('group_to_wallet_mappings')
    op.drop_index(op.f('ix_wallets_name'), table_name='wallets')
    op.drop_index(op.f('ix_wallets_id'), table_name='wallets')
    op.drop_table('wallets')
    # ### end Alembic commands ###
