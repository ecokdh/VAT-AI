# Track A: POST /auth/register, POST /auth/login, GET /auth/me 테스트. api-spec.md §3.1 참고.
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_login_me_flow():
    res = client.post("/auth/register", json={"email": "test@example.com", "password": "pw1234", "name": "테스트"})
    assert res.status_code == 201
    token = res.json()["access_token"]

    dup = client.post("/auth/register", json={"email": "test@example.com", "password": "pw1234", "name": "테스트"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    login = client.post("/auth/login", json={"email": "test@example.com", "password": "pw1234"})
    assert login.status_code == 200

    bad_login = client.post("/auth/login", json={"email": "test@example.com", "password": "wrong"})
    assert bad_login.status_code == 401

    no_auth = client.get("/auth/me")
    assert no_auth.status_code == 401

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"

def test_register_validation_error():
    res = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "pw", "name": "테스트"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"