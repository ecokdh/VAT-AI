"""add v2 transactions and analysis runs

Revision ID: 3ad4b892c761
Revises: 015d7b1f7bdb
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "3ad4b892c761"
down_revision: Union[str, Sequence[str], None] = "015d7b1f7bdb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("processing_stage", sqlmodel.sql.sqltypes.AutoString(), nullable=True, server_default="queued"))
    op.add_column("receipts", sa.Column("processing_progress", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("receipts", sa.Column("stage_statuses_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='{"photo_quality":"pending","text_recognition":"pending","transaction_extraction":"pending","missing_field_check":"pending"}'))
    op.add_column("receipts", sa.Column("ocr_warnings_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    op.add_column("receipts", sa.Column("ocr_pipeline_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("receipts", sa.Column("ocr_pipeline_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("receipts", sa.Column("ocr_missing_fields_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"))
    op.add_column("receipts", sa.Column("extraction_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("receipts", sa.Column("ocr_user_attempts", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("receipts", sa.Column("retention_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="under_review"))
    op.create_index("ix_receipts_extraction_confirmed", "receipts", ["extraction_confirmed"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=True),
        sa.Column("direction", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("vendor", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""),
        sa.Column("purpose", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("evidence_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="unknown"),
        sa.Column("business_related", sa.Boolean(), nullable=True),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("supply_amount", sa.Integer(), nullable=True),
        sa.Column("vat_amount", sa.Integer(), nullable=True),
        sa.Column("tax_treatment", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="unknown"),
        sa.Column("state", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="draft"),
        sa.Column("state_before_delete", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="not_analyzed"),
        sa.Column("risk_level", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("deductible_vat", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deemed_input_supply", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deemed_input_eligible", sa.Boolean(), nullable=True),
        sa.Column("deemed_input_document_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("analysis_reason", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("legal_references_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("retention_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="under_review"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("permanent_delete_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.UniqueConstraint("receipt_id"),
    )
    for name, column in (
        ("ix_transactions_user_id", "user_id"),
        ("ix_transactions_direction", "direction"),
        ("ix_transactions_transaction_date", "transaction_date"),
        ("ix_transactions_state", "state"),
        ("ix_transactions_review_status", "review_status"),
        ("ix_transactions_deleted_at", "deleted_at"),
    ):
        op.create_index(name, "transactions", [column])

    op.create_table(
        "transaction_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.UniqueConstraint("transaction_id", "revision", name="uq_transaction_revision"),
    )
    op.create_index("ix_transaction_revisions_transaction_id", "transaction_revisions", ["transaction_id"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_ids_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="PENDING"),
        sa.Column("result_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_analysis_runs_user_id", "analysis_runs", ["user_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])

    op.create_table(
        "tax_profiles_v2",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("industry_category", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("industry_subtype", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_sme", sa.Boolean(), nullable=True),
        sa.Column("simplified_industry_rate", sa.Integer(), nullable=True),
        sa.Column("taxable_sales_h1", sa.Integer(), nullable=True),
        sa.Column("taxable_sales_h2", sa.Integer(), nullable=True),
        sa.Column("deemed_related_taxable_sales_h1", sa.Integer(), nullable=True),
        sa.Column("deemed_related_taxable_sales_h2", sa.Integer(), nullable=True),
        sa.Column("business_start_date", sa.Date(), nullable=True),
        sa.Column("business_end_date", sa.Date(), nullable=True),
        sa.Column("suspension_periods_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="[]"),
        sa.Column("tax_type_change_date", sa.Date(), nullable=True),
        sa.Column("changed_to_tax_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_tax_profiles_v2_user_id", "tax_profiles_v2", ["user_id"])

    op.create_table(
        "async_jobs",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="PENDING"),
        sa.Column("result_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_async_jobs_user_id", "async_jobs", ["user_id"])
    op.create_index("ix_async_jobs_job_type", "async_jobs", ["job_type"])
    op.create_index("ix_async_jobs_status", "async_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_async_jobs_status", table_name="async_jobs")
    op.drop_index("ix_async_jobs_job_type", table_name="async_jobs")
    op.drop_index("ix_async_jobs_user_id", table_name="async_jobs")
    op.drop_table("async_jobs")
    op.drop_index("ix_tax_profiles_v2_user_id", table_name="tax_profiles_v2")
    op.drop_table("tax_profiles_v2")
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_user_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_transaction_revisions_transaction_id", table_name="transaction_revisions")
    op.drop_table("transaction_revisions")
    for name in (
        "ix_transactions_deleted_at",
        "ix_transactions_review_status",
        "ix_transactions_state",
        "ix_transactions_transaction_date",
        "ix_transactions_direction",
        "ix_transactions_user_id",
    ):
        op.drop_index(name, table_name="transactions")
    op.drop_table("transactions")
    op.drop_column("receipts", "ocr_pipeline_version")
    op.drop_column("receipts", "ocr_pipeline_name")
    op.drop_index("ix_receipts_extraction_confirmed", table_name="receipts")
    op.drop_column("receipts", "retention_status")
    op.drop_column("receipts", "ocr_user_attempts")
    op.drop_column("receipts", "extraction_confirmed")
    op.drop_column("receipts", "ocr_missing_fields_json")
    op.drop_column("receipts", "ocr_warnings_json")
    op.drop_column("receipts", "stage_statuses_json")
    op.drop_column("receipts", "processing_progress")
    op.drop_column("receipts", "processing_stage")
