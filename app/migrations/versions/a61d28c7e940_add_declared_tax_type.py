"""Keep user-declared tax type separate from verified NTS facts."""
from alembic import op
import sqlalchemy as sa

revision = "a61d28c7e940"
down_revision = "9b2d5e7f1031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tax_profiles_v2", sa.Column("tax_type", sa.String(), nullable=True))


def downgrade():
    op.drop_column("tax_profiles_v2", "tax_type")
