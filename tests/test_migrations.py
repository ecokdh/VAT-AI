import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


def test_upgrade_existing_prototype_preserves_receipt(tmp_path):
    """Upgrade the already published OCR head, without restamping or data reset."""
    database_url = f"sqlite:///{(tmp_path / 'existing.db').as_posix()}"
    environment = {**os.environ, 'DB_URL': database_url, 'JWT_SECRET': 'migration-test-only'}
    def upgrade(revision):
        result = subprocess.run([sys.executable, '-B', '-m', 'alembic', 'upgrade', revision],
            cwd=Path(__file__).parents[1], env=environment, capture_output=True, encoding='utf-8', errors='replace')
        assert result.returncode == 0, result.stdout + result.stderr
    upgrade('e1a2b3c4d5e6')
    from sqlmodel import Session
    from app.receipts.models import Receipt
    engine = create_engine(database_url)
    # 그 시점 스키마에 있는 칸만 SQL로 넣는다. 현재 ORM 모델에는 뒤에 추가된 칸(nickname 등)이 있다.
    with engine.begin() as connection:
        user_id = uuid4().hex
        connection.execute(text("INSERT INTO users (id, email, password_hash, name, created_at) VALUES (:id, 'migration@example.com', 'fixture', '검증', CURRENT_TIMESTAMP)"), {'id': user_id})
        rid = connection.execute(text("INSERT INTO receipts (user_id, image_url, status, vendor, amount, ocr_raw, created_at) "
                                      "VALUES (:user_id, 'preserved.png', 'done', :vendor, 1000, :ocr_raw, CURRENT_TIMESTAMP)"),
                                 {'user_id': user_id, 'vendor': '유지할 상호', 'ocr_raw': '{"original":true}'}).lastrowid
    upgrade('head')
    with Session(engine) as session:
        receipt = session.get(Receipt, rid)
        assert receipt.vendor == '유지할 상호' and receipt.amount == 1000
        assert receipt.ocr_raw == '{"original":true}' and receipt.image_url == 'preserved.png'


def test_alembic_upgrade_head_creates_legacy_and_v2_schema(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment["DB_URL"] = database_url
    environment["JWT_SECRET"] = "migration-test-only"

    result = subprocess.run(
        [sys.executable, "-B", "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            "users",
            "receipts",
            "deductions",
            "business_profiles",
            "transactions",
            "transaction_revisions",
            "analysis_runs",
            "tax_profiles_v2",
            "async_jobs",
            "consent_records",
            "law_embeddings",
            "password_reset_tokens",
            "team_benchmark_members",
            "team_benchmark_cases",
            "merchant_memories",
            "filing_inputs",
            "monthly_sales_documents",
        }
        consent_columns = {
            column["name"] for column in inspect(connection).get_columns("consent_records")
        }
        assert consent_columns == {
            "id", "user_id", "consent_type", "accepted", "document_version", "recorded_at",
        }
        receipt_columns = {column["name"] for column in inspect(connection).get_columns("receipts")}
        assert {
            "processing_stage", "processing_progress", "stage_statuses_json",
            "ocr_warnings_json", "ocr_pipeline_name", "ocr_pipeline_version",
        }.issubset(receipt_columns)
        columns = {column["name"]: column for column in inspect(connection).get_columns("business_profiles")}
        assert set(columns) == {
            "id", "user_id", "business_number", "business_name", "business_status",
            "business_status_code", "tax_type", "tax_type_code", "end_date",
            "verification_status", "verified_at", "created_at",
            "business_address", "business_type", "business_item", "industry_code",
        }
        for name in ("id", "user_id", "business_number", "verification_status", "created_at"):
            assert not columns[name]["nullable"]
        assert any(
            fk["constrained_columns"] == ["user_id"]
            and fk["referred_table"] == "users"
            and fk["referred_columns"] == ["id"]
            for fk in inspect(connection).get_foreign_keys("business_profiles")
        )
        assert any(
            constraint["column_names"] == ["user_id"]
            for constraint in inspect(connection).get_unique_constraints("business_profiles")
        )
        assert not any(
            "business_number" in index["column_names"]
            for index in inspect(connection).get_indexes("business_profiles")
        )
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert "direction" in receipt_columns
        assert {"doc_type", "support_status", "readability_issues_json", "affected_regions_json", "issue_code", "guide_message", "classification_version"}.issubset(receipt_columns)
        # 최신 리비전을 적어 두면 마이그레이션이 추가될 때마다 깨지므로 alembic이 아는 head와 비교한다.
        assert revision == ScriptDirectory.from_config(Config(str(Path(__file__).parents[1] / "alembic.ini"))).get_current_head()
        assert {"id", "business_number", "business_name", "tax_type", "source", "hit_count"}.issubset({c["name"] for c in inspect(connection).get_columns("merchant_memories")})
        assert {'business_description','operating_industry','has_employees','onboarding_completed','tax_type'} <= {c['name'] for c in inspect(connection).get_columns('tax_profiles_v2')}
        assert {'question_answers_json','question_rule_version'} <= {c['name'] for c in inspect(connection).get_columns('transactions')}
