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
            "business_profiles",
        }
        columns = {column["name"]: column for column in inspect(connection).get_columns("business_profiles")}
        assert set(columns) == {
            "id", "user_id", "business_number", "business_name", "business_status",
            "business_status_code", "tax_type", "tax_type_code", "end_date",
            "verification_status", "verified_at", "created_at",
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
        assert revision == "015d7b1f7bdb"
