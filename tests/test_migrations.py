import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_head_creates_a_base_schema(tmp_path: Path):
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
            "transactions",
            "line_items",
            "reconciliation_issues",
        }
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert revision == "20261005a5"
        columns = {column["name"] for column in inspect(connection).get_columns("receipts")}
        assert {"taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount", "money_sources_json", "subtotal_amount", "item_amounts_json"} <= columns
        assert "money_schema_version" in columns


def test_money_migration_preserves_legacy_values(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = {**os.environ, "DB_URL": database_url, "JWT_SECRET": "migration-test-only"}

    def migrate(*args):
        result = subprocess.run([sys.executable, "-B", "-m", "alembic", *args],
            cwd=Path(__file__).parents[1], env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    migrate("upgrade", "20261002a1")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id,email,password_hash,name,created_at) VALUES (:id,'legacy@example.com','x','legacy','2026-10-05')"), {"id": "a" * 32})
        connection.execute(text("INSERT INTO receipts (user_id,image_url,vendor,amount,supply_amount,vat_amount,status,confirmed,created_at) VALUES (:id,'old.png','old',18780,18237,543,'done',1,'2026-10-05')"), {"id": "a" * 32})
        connection.execute(text("UPDATE receipts SET items_json=:items"), {"items": '["repeat","repeat"]'})
    migrate("upgrade", "head")
    with engine.connect() as connection:
        row = connection.execute(text("SELECT amount,supply_amount,vat_amount,confirmed,taxable_supply_amount,tax_exempt_amount,transaction_amount,payment_amount,money_sources_json,subtotal_amount,item_amounts_json,money_schema_version FROM receipts")).one()
        assert tuple(row) == (18780, 18237, 543, 1, None, None, None, None, None, None, None, 1)
        items = connection.execute(text("SELECT id,position,data_json FROM line_items ORDER BY position")).all()
        assert len(items) == 2 and items[0].id != items[1].id
        assert [item.position for item in items] == [0, 1]
        import json
        assert all(json.loads(item.data_json)["quantity"] is None for item in items)
        assert connection.execute(text("SELECT items_json,revision FROM receipts")).one() == ('["repeat","repeat"]', 1)
        assert any(fk["referred_table"] == "transactions" for fk in inspect(connection).get_foreign_keys("receipts"))
        transaction = connection.execute(text("SELECT id,data_json,workflow_status FROM transactions")).one()
        facts = json.loads(transaction.data_json)
        assert facts["supply_amount"] == 18237
        assert facts["taxable_supply_amount"] is None and facts["tax_exempt_amount"] is None
        assert facts["total_amount"] == 18780 and facts["vat_amount"] == 543
        assert facts["ocr_confirmed"] is True and facts["tax_analysis_confirmed"] is False
        assert facts["legacy_confirmation"]["money_schema_version"] == 1
        assert transaction.workflow_status == "NEEDS_CONTEXT"
        assert connection.execute(text("SELECT transaction_id FROM receipts")).scalar_one() == transaction.id
    # Historical facts and structured items are available through the same owned transaction contract.
    from sqlmodel import Session
    from app.receipts.transactions import owned_transaction, transaction_out
    import uuid
    with Session(engine) as session:
        owner = uuid.UUID("a" * 32)
        result = transaction_out(session, owner, owned_transaction(session, owner, transaction.id))
        assert len(result["receipts"]) == 1 and result["receipts"][0]["confirmed"] is True
        assert [item["name"] for item in result["canonical_line_items"]] == ["repeat", "repeat"]
        assert result["evidence_validation"]["validation_status"] == "INCOMPLETE"
        assert result["tax_analysis_confirmed"] is False
    migrate("downgrade", "20261005a3")
    migrate("upgrade", "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM transactions")).scalar_one() == transaction.id
        assert connection.execute(text("SELECT revision FROM receipts")).scalar_one() == 1
    migrate("downgrade", "20261002a1")
    with engine.connect() as connection:
        assert tuple(connection.execute(text("SELECT amount,supply_amount,vat_amount,confirmed FROM receipts")).one()) == (18780, 18237, 543, 1)


def test_confirmed_transaction_backfill_preserves_existing_links_and_signed_facts(tmp_path):
    import json
    database_url = f"sqlite:///{(tmp_path / 'confirmed.db').as_posix()}"
    environment = {**os.environ, "DB_URL": database_url, "JWT_SECRET": "migration-test-only"}

    def migrate(target):
        result = subprocess.run([sys.executable, "-B", "-m", "alembic", "upgrade", target],
            cwd=Path(__file__).parents[1], env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    migrate("20261005a3")
    engine = create_engine(database_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,password_hash,name,created_at) VALUES (:id,'backfill@example.com','x','test','2026-10-05')"), {"id": "b" * 32})
        c.execute(text("INSERT INTO transactions (id,user_id,data_json,revision,workflow_status) VALUES ('existing',:id,:data,7,'NEEDS_CONTEXT')"),
            {"id": "b" * 32, "data": '{"total_amount":42}'})
        for identifier, confirmed, linked, amount, transaction_amount, document in (
            (1, True, "existing", 42, 42, {}),
            (2, False, None, 100, None, {}),
            (3, True, None, -1100, -1100, {"adjustment_type": "RETURN"}),
            (4, True, None, -1100, None, {}),
            (5, True, None, 999, 1100, {}),
        ):
            c.execute(text("INSERT INTO receipts (id,user_id,image_url,vendor,amount,transaction_amount,taxable_supply_amount,tax_exempt_amount,vat_amount,status,confirmed,created_at,revision,transaction_id,document_json,money_schema_version) "
                "VALUES (:id,:user,'old.png','상점',:amount,:total,:net,0,:vat,'done',:confirmed,'2026-10-05',3,:linked,:document,2)"),
                {"id": identifier, "user": "b" * 32, "amount": amount, "total": transaction_amount,
                    "net": -1000 if amount < 0 else 1000, "vat": -100 if amount < 0 else 100,
                    "confirmed": confirmed, "linked": linked, "document": json.dumps(document)})
        before = [dict(row) for row in c.execute(text("SELECT * FROM receipts ORDER BY id")).mappings()]
        c.execute(text("INSERT INTO reconciliation_issues (id,user_id,receipt_id,candidate_receipt_id,reason,resolved,action) "
            "VALUES ('legacy-decision',:user,2,5,'SIMILAR_IMAGE',1,'SEPARATE')"), {"user": "b" * 32})
    migrate("head")
    migrate("head")
    with engine.connect() as c:
        after = [dict(row) for row in c.execute(text("SELECT * FROM receipts ORDER BY id")).mappings()]
        for old, new in zip(before, after):
            assert {k: v for k, v in new.items() if k != "transaction_id"} == {k: v for k, v in old.items() if k != "transaction_id"}
        assert after[0]["transaction_id"] == "existing" and after[1]["transaction_id"] is None
        existing = c.execute(text("SELECT data_json,revision FROM transactions WHERE id='existing'")).one()
        assert tuple(existing) == ('{"total_amount":42}', 7)
        assert c.execute(text("SELECT count(*) FROM transactions")).scalar_one() == 4
        transactions = {json.loads(row.data_json)["source_receipt_id"]: row for row in c.execute(text("SELECT * FROM transactions WHERE id!='existing'"))}
        for identifier in (3, 4):
            row = transactions[identifier]
            assert row.workflow_status == "UNRESOLVED_ADJUSTMENT" and row.original_transaction_id is None
            facts = json.loads(row.data_json)
            assert (facts["total_amount"], facts["taxable_supply_amount"], facts["tax_exempt_amount"], facts["vat_amount"]) == (-1100, -1000, 0, -100)
        assert transactions[3].adjustment_type == "RETURN" and transactions[4].adjustment_type is None
        assert json.loads(transactions[5].data_json)["total_amount"] == 1100
        decision = c.execute(text("SELECT id,resolved,action,active FROM reconciliation_issues")).one()
        assert tuple(decision) == ("legacy-decision", 1, "SEPARATE", 1)
        assert any(constraint["name"] == "uq_reconciliation_receipt_pair" for constraint in inspect(c).get_unique_constraints("reconciliation_issues"))
        assert not c.execute(text("PRAGMA foreign_key_check")).all()
