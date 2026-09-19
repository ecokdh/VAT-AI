import pytest


def test_register_login_and_me(client):
    register = client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-password",
            "name": "김대표",
        },
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    assert register.json()["user"]["email"] == "owner@example.com"

    login = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct-password"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["name"] == "김대표"


def test_duplicate_register_and_invalid_login_use_contract_errors(client):
    body = {
        "email": "owner@example.com",
        "password": "correct-password",
        "name": "김대표",
    }
    assert client.post("/auth/register", json=body).status_code == 201

    duplicate = client.post("/auth/register", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    invalid = client.post(
        "/auth/login",
        json={"email": body["email"], "password": "wrong-password"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.parametrize("password", ["x" * 72, "한" * 24])
def test_passwords_within_bcrypt_utf8_boundary_are_accepted(client, password):
    response = client.post(
        "/auth/register",
        json={
            "email": "boundary@example.com",
            "password": password,
            "name": "경계값",
        },
    )
    assert response.status_code == 201


def test_password_over_bcrypt_utf8_boundary_is_json_validation_error(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "too-long@example.com",
            "password": "한" * 25,
            "name": "경계 초과",
        },
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
