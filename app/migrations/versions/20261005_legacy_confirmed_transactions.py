"""Link historical confirmations without reinterpreting their recorded amounts."""
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision = "20261005a4"
down_revision = "20261005a3"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    receipts = connection.execute(sa.text(
        "SELECT * FROM receipts WHERE confirmed = :confirmed AND transaction_id IS NULL ORDER BY id"
    ), {"confirmed": True}).mappings().all()
    for receipt in receipts:
        document = json.loads(receipt["document_json"] or "{}")
        adjustment = document.get("adjustment_type")
        transaction_id = str(uuid.uuid5(uuid.NAMESPACE_URL,
            f"vat-ai/legacy-confirmed/{receipt['user_id']}/{receipt['id']}"))
        facts = {
            "schema_version": 1, "source_receipt_id": receipt["id"],
            "vendor": receipt["vendor"], "vendor_business_number": receipt["business_number"],
            "date": str(receipt["date"]) if receipt["date"] is not None else None,
            "supply_amount": receipt["supply_amount"],
            "taxable_supply_amount": receipt["taxable_supply_amount"],
            "tax_exempt_amount": receipt["tax_exempt_amount"], "vat_amount": receipt["vat_amount"],
            "total_amount": receipt["transaction_amount"] if receipt["transaction_amount"] is not None else receipt["amount"],
            "payment_amount": receipt["payment_amount"], "subtotal_amount": receipt["subtotal_amount"],
            "document": document, "ocr_confirmed": True, "tax_analysis_confirmed": False,
            "legacy_confirmation": {"migration": revision, "money_schema_version": receipt["money_schema_version"]},
        }
        connection.execute(sa.text(
            "INSERT INTO transactions (id,user_id,data_json,revision,workflow_status,original_transaction_id,adjustment_type) "
            "VALUES (:id,:user_id,:data,1,:status,NULL,:adjustment)"
        ), {"id": transaction_id, "user_id": receipt["user_id"], "data": json.dumps(facts, ensure_ascii=False),
            "status": "UNRESOLVED_ADJUSTMENT" if adjustment or (facts["total_amount"] is not None and facts["total_amount"] < 0) else "NEEDS_CONTEXT",
            "adjustment": adjustment})
        # A historical confirmation is retained, not confirmed again: no revision/status/amount changes.
        connection.execute(sa.text("UPDATE receipts SET transaction_id=:transaction WHERE id=:receipt"),
            {"transaction": transaction_id, "receipt": receipt["id"]})


def downgrade():
    # The previous schema supports these rows. Preserve subsequent evidence links and user edits.
    # An upgrade after downgrade skips linked receipts, so it never duplicates their transactions.
    pass
