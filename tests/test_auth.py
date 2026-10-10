import pytest

from app.auth import service as auth_service
from app.business.schemas import BusinessVerifyResponse


@pytest.fixture(autouse=True)
def mock_business_verification(monkeypatch):
    monkeypatch.setattr(auth_service, "verify_business", lambda _: BusinessVerifyResponse(
        business_number="1234567890", business_status="계속사업자",
        business_status_code="01", tax_type="부가가치세 일반과세자",
        tax_type_code="01", verified=True,
    ))


def register_body(email="owner@example.com", password="correct-password"):
    return {
        "email": email, "password": password, "name": "Owner",
        "business_name": "Owner Store", "business_number": "123-45-67890",
        "terms_accepted": True, "privacy_accepted": True, "marketing_accepted": False,
    }


def test_register_login_and_me(client):
    register = client.post("/auth/register", json=register_body())
    assert register.status_code == 201
    token = register.json()["access_token"]
    assert register.json()["user"]["email"] == "owner@example.com"
    assert "terms_accepted_at" not in register.json()["user"]

    login = client.post("/auth/login", json={"email": "owner@example.com", "password": "correct-password"})
    assert login.status_code == 200
    assert login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Owner"
    assert me.json()["business"]["business_number"] == "1234567890"
    assert "password_hash" not in str(me.json())


def test_duplicate_register_and_invalid_login_use_contract_errors(client):
    body = register_body()
    assert client.post("/auth/register", json=body).status_code == 201

    duplicate = client.post("/auth/register", json=body)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    invalid = client.post("/auth/login", json={"email": body["email"], "password": "wrong-password"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_email_availability_check_handles_new_and_registered_emails(client):
    available = client.post("/auth/email-availability", json={"email": "new@example.com"})
    assert available.status_code == 200
    assert available.json() == {"available": True}

    assert client.post("/auth/register", json=register_body()).status_code == 201
    registered = client.post("/auth/email-availability", json={"email": "OWNER@example.com"})
    assert registered.status_code == 200
    assert registered.json() == {"available": False}


def test_email_availability_check_rejects_invalid_email(client):
    response = client.post("/auth/email-availability", json={"email": "not-an-email"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("password", ["x" * 72, "가" * 24])
def test_passwords_within_bcrypt_utf8_boundary_are_accepted(client, password):
    response = client.post("/auth/register", json=register_body("boundary@example.com", password))
    assert response.status_code == 201


def test_password_over_bcrypt_utf8_boundary_is_json_validation_error(client):
    response = client.post("/auth/register", json=register_body("too-long@example.com", "가" * 25))
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("field", ["terms_accepted", "privacy_accepted"])
def test_registration_requires_mandatory_consents(client, field):
    body = register_body()
    body[field] = False

    response = client.post("/auth/register", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"
