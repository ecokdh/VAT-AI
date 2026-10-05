"""Document provenance, revisions, structured items and transaction links."""
from alembic import op
import sqlalchemy as sa
import json
import uuid

revision = "20261005a3"
down_revision = "20261005a2"
branch_labels = depends_on = None


def upgrade():
    op.create_table("transactions", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("data_json", sa.String(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("workflow_status", sa.String(), nullable=False),
        sa.Column("original_transaction_id", sa.String(), sa.ForeignKey("transactions.id")),
        sa.Column("adjustment_type", sa.String()))
    for name, kind in (("document_json", sa.String()), ("ocr_response_json", sa.String()),
                       ("file_hash", sa.String()), ("perceptual_hash", sa.String()), ("transaction_id", sa.String())):
        op.add_column("receipts", sa.Column(name, kind, nullable=True))
    op.add_column("receipts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    with op.batch_alter_table("receipts") as batch:
        batch.create_foreign_key("fk_receipts_transaction_id", "transactions", ["transaction_id"], ["id"])
    op.create_table("line_items", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("data_json", sa.String(), nullable=False))
    op.create_table("reconciliation_issues", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("candidate_receipt_id", sa.Integer(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("reason", sa.String(), nullable=False), sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("action", sa.String()))
    for table, field in (("transactions", "user_id"), ("line_items", "receipt_id"), ("reconciliation_issues", "user_id"), ("receipts", "file_hash"), ("receipts", "transaction_id")):
        op.create_index(f"ix_{table}_{field}", table, [field])
    connection = op.get_bind()
    for receipt in connection.execute(sa.text("SELECT id,items_json,item_amounts_json FROM receipts")).mappings():
        names = json.loads(receipt["items_json"] or "[]")
        numbers = {row["item_index"]: row for row in json.loads(receipt["item_amounts_json"] or "[]")}
        for position, name in enumerate(names):
            row = numbers.get(position, {})
            item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vat-ai/receipts/{receipt['id']}/items/{position}"))
            printed_price = row.get("unit_price") if row.get("sources", {}).get("unit_price", {}).get("kind") != "calculated" else None
            data = {"id": item_id, "name": name, "original_name": name, "quantity": row.get("quantity"),
                    "printed_unit_price": printed_price, "effective_unit_price": None,
                    "line_amount": row.get("line_amount"), "sources": {}}
            connection.execute(sa.text("INSERT INTO line_items (id,receipt_id,position,data_json) VALUES (:id,:receipt_id,:position,:data)"),
                               {"id": item_id, "receipt_id": receipt["id"], "position": position, "data": json.dumps(data, ensure_ascii=False)})


def downgrade():
    for table in ("reconciliation_issues", "line_items"):
        op.drop_table(table)
    for field in ("transaction_id", "file_hash"):
        op.drop_index(f"ix_receipts_{field}", table_name="receipts")
    with op.batch_alter_table("receipts") as batch:
        batch.drop_constraint("fk_receipts_transaction_id", type_="foreignkey")
        for name in ("revision", "transaction_id", "perceptual_hash", "file_hash", "ocr_response_json", "document_json"):
            batch.drop_column(name)
    op.drop_table("transactions")
