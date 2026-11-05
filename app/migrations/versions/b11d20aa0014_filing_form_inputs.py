"""Inputs for the VAT return form: business filing info, fixed-asset flag, preliminary notice tax."""
from alembic import op
import sqlalchemy as sa

revision = "b11d20aa0014"
down_revision = "a10c19aa0013"
branch_labels = None
depends_on = None


def upgrade():
    # 신고서 머리 칸(사업장 주소)과 과세표준명세(업태·종목·업종코드)
    op.add_column("business_profiles", sa.Column("business_address", sa.String(length=255), nullable=True))
    op.add_column("business_profiles", sa.Column("business_type", sa.String(length=100), nullable=True))
    op.add_column("business_profiles", sa.Column("business_item", sa.String(length=100), nullable=True))
    op.add_column("business_profiles", sa.Column("industry_code", sa.String(length=6), nullable=True))
    # 신고서 (12) 고정자산매입 구분
    op.add_column("transactions", sa.Column("is_fixed_asset", sa.Boolean(), nullable=False, server_default=sa.false()))
    # 신고서 (24) 예정고지세액: 사용자·신고기간마다 하나
    op.create_table(
        "filing_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("preliminary_notice_tax", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "period", name="uq_filing_inputs_user_period"),
    )
    op.create_index("ix_filing_inputs_user_id", "filing_inputs", ["user_id"])


def downgrade():
    op.drop_index("ix_filing_inputs_user_id", table_name="filing_inputs")
    op.drop_table("filing_inputs")
    op.drop_column("transactions", "is_fixed_asset")
    for name in ("industry_code", "business_item", "business_type", "business_address"):
        op.drop_column("business_profiles", name)
