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
        }
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert revision == "0632cbc850ef"
