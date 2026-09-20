# Track A: POST /auth/register, POST /auth/login, GET /auth/me 테스트. api-spec.md §3.1 참고.
import uuid  # [수정] 매 실행마다 랜덤 이메일을 만들기 위해 추가

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_login_me_flow():
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"  # [수정] 고정 이메일 대신 매번 새 랜덤 이메일 생성 (DB에 남은 이전 데이터와 충돌 방지)

    res = client.post("/auth/register", json={"email": email, "password": "pw1234", "name": "테스트"})  # [수정] "test@example.com" → email
    assert res.status_code == 201
    token = res.json()["access_token"]

    dup = client.post("/auth/register", json={"email": email, "password": "pw1234", "name": "테스트"})  # [수정] "test@example.com" → email
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    login = client.post("/auth/login", json={"email": email, "password": "pw1234"})  # [수정] "test@example.com" → email
    assert login.status_code == 200

    bad_login = client.post("/auth/login", json={"email": email, "password": "wrong"})  # [수정] "test@example.com" → email
    assert bad_login.status_code == 401

    no_auth = client.get("/auth/me")
    assert no_auth.status_code == 401

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email  # [수정] "test@example.com" → email

def test_register_validation_error():
    res = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "pw", "name": "테스트"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"