from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.core.database import get_session
from app.main import app
from app.receipts import service as receipt_service
from app.receipts.storage import LocalFileStorage


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr(
        receipt_service, "storage", LocalFileStorage(tmp_path / "storage")
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

