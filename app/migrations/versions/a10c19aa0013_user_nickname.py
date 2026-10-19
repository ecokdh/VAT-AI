"""Separate display nickname from the verified representative name."""
from alembic import op
import sqlalchemy as sa

revision = "a10c19aa0013"
down_revision = "f2b3c4d5e6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("nickname", sa.String(length=20), nullable=True))


def downgrade():
    op.drop_column("users", "nickname")
