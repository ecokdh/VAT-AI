"""Complete main's prerequisites for databases upgraded on the former track-ocr chain."""

from importlib import import_module

from alembic import op
import sqlalchemy as sa

revision = "c42f50aa0016"
down_revision = "c31e40aa0015"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "nickname" not in {column["name"] for column in inspector.get_columns("users")}:
        import_module("app.migrations.versions.a10c19aa0013_user_nickname").upgrade()
    if not inspector.has_table("filing_inputs"):
        import_module("app.migrations.versions.b11d20aa0014_filing_form_inputs").upgrade()


def downgrade():
    # These columns and table belong to earlier revisions on the merged chain.
    pass
