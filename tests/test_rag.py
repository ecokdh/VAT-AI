import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.deduction.rag import load_laws as loader
from app.deduction.rag import service
from app.deduction.rag.models import LawEmbedding
from app.deduction.rag.schemas import LawEmbedIn


LAW = {"source": "부가가치세법", "article": "제38조", "content": "공제하는 매입세액"}


@pytest.fixture()
def admin_key(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(service, "get_embedding", lambda text: [0.1] * 1536)
    return "test-admin-key"


def test_embed_law_with_admin_key(client, admin_key):
    response = client.post("/rag/embed", json=LAW, headers={"X-Admin-Key": admin_key})

    assert response.status_code == 201
    assert response.json() == {"id": 1, **LAW}


def test_embed_law_rejects_wrong_key(client, admin_key):
    response = client.post("/rag/embed", json=LAW, headers={"X-Admin-Key": "wrong"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_embed_law_rejects_when_admin_key_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "")
    response = client.post("/rag/embed", json=LAW, headers={"X-Admin-Key": ""})

    assert response.status_code == 403


def test_load_laws_batches_embeddings_and_replaces_same_source(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(loader, "BATCH_SIZE", 2)
    monkeypatch.setattr(loader, "get_embeddings", lambda texts: calls.append(texts) or [[0.1] * 1536] * len(texts))
    engine = create_engine(f"sqlite:///{tmp_path / 'laws.db'}")
    SQLModel.metadata.create_all(engine)
    laws = [LawEmbedIn(source="부가가치세법", article=f"제{n}조", content=f"내용 {n}") for n in range(1, 4)]

    with Session(engine) as session:
        loader.load_laws(session, laws)
        loader.load_laws(session, laws[:1])
        stored = session.exec(select(LawEmbedding.article)).all()

    assert [len(batch) for batch in calls] == [2, 1, 1]
    assert stored == ["제1조"]


def test_get_laws_returns_requested_order_and_skips_missing(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'laws.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        for article in ("제38조 제1항", "제39조 제1항"):
            session.add(LawEmbedding(source="부가가치세법", article=article, content=article, embedding=[0.1] * 1536))
        session.commit()
        laws = service.get_laws(session, [
            ("부가가치세법", "제39조 제1항"),
            ("부가가치세법 시행령", "제77조"),
            ("부가가치세법", "제38조 제1항"),
        ])

    assert [law.article for law in laws] == ["제39조 제1항", "제38조 제1항"]
