"""merge performance indexes and remove run_time_str

Revision ID: b5c21d244111
Revises: c5892216, 2b924cdc9f45
Create Date: 2026-01-06 15:17:40.651674

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c21d244111'
down_revision: Union[str, None] = ('c5892216', '2b924cdc9f45')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
