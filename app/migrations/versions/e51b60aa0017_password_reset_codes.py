"""Add limited-attempt email codes to password recovery."""
from alembic import op
import sqlalchemy as sa

revision = "e51b60aa0017"
down_revision = "e52a60aa0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("password_reset_tokens", sa.Column("code_hash", sa.String(64), nullable=True))
    op.add_column("password_reset_tokens", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("password_reset_tokens", sa.Column("verified_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("password_reset_tokens") as batch:
        batch.drop_column("verified_at")
        batch.drop_column("attempts")
        batch.drop_column("code_hash")
