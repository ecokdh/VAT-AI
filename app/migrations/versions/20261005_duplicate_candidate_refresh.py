"""Keep candidate activity separate from the user's reconciliation decision."""
from alembic import op
import sqlalchemy as sa

revision = "20261005a5"
down_revision = "20261005a4"
branch_labels = depends_on = None


def upgrade():
    op.add_column("reconciliation_issues", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("reconciliation_issues") as batch:
        batch.create_unique_constraint("uq_reconciliation_receipt_pair", ["receipt_id", "candidate_receipt_id"])


def downgrade():
    with op.batch_alter_table("reconciliation_issues") as batch:
        batch.drop_constraint("uq_reconciliation_receipt_pair", type_="unique")
        batch.drop_column("active")
