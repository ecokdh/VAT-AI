"""Account recovery, first capture guide, and editable OCR details."""
from alembic import op
import sqlalchemy as sa

revision = "b72c4e91f630"
down_revision = "a3f1c2d4e5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("ocr_guide_seen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("receipts", sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"))
    op.create_table("password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True))
    for field in ("email_hash", "ip_hash", "created_at"):
        op.create_index(f"ix_password_reset_tokens_{field}", "password_reset_tokens", [field])


def downgrade():
    op.drop_table("password_reset_tokens")
    op.drop_column("receipts", "details_json")
    op.drop_column("users", "ocr_guide_seen")
    op.drop_column("users", "token_version")
