from datetime import date

import pytest

from app.business import service, nts_client
from app.business.schemas import BusinessVerifyResponse
from app.common.exceptions import AppException


@pytest.fixture
def identity_payload():
    return {"business_number": "123-45-67890", "representative_name": "  대표자  ",
            "business_name": "  테스트 상호  ", "business_start_date": "2025-01-01"}


@pytest.fixture
def status_lookup(monkeypatch):
    seen = []
    def lookup(number):
        seen.append(number)
        return BusinessVerifyResponse(business_number="1234567890", business_status="계속사업자",
            business_status_code="01", tax_type="일반과세", tax_type_code="01", verified=True)
    monkeypatch.setattr(service, "verify_business", lookup)
    return seen


def test_single_signup_verification_checks_all_four_and_returns_tax_type(client, identity_payload, status_lookup, monkeypatch):
    seen = []
    monkeypatch.setattr(nts_client, "validate_identity", lambda *args: seen.append(args))
    response = client.post("/business/verify-identity", json=identity_payload)
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert response.json()["business_number"] == "1234567890"
    assert response.json()["tax_type_code"] == "01"
    assert status_lookup == ["123-45-67890"]
    assert seen == [("1234567890", "대표자", "20250101", "테스트 상호")]


@pytest.mark.parametrize("field", ["business_number", "representative_name", "business_name", "business_start_date"])
def test_signup_verification_rejects_missing_fields(client, identity_payload, status_lookup, field):
    del identity_payload[field]
    assert client.post("/business/verify-identity", json=identity_payload).status_code == 400
    assert status_lookup == []


@pytest.mark.parametrize("field", ["representative_name", "business_name"])
def test_signup_verification_rejects_blank_identity_text(client, identity_payload, status_lookup, field):
    identity_payload[field] = "  "
    assert client.post("/business/verify-identity", json=identity_payload).status_code == 400
    assert status_lookup == []


def test_status_success_does_not_mask_identity_mismatch(client, identity_payload, status_lookup, monkeypatch):
    def mismatch(*_):
        raise AppException(400, "BUSINESS_IDENTITY_MISMATCH", "등록정보 불일치")
    monkeypatch.setattr(nts_client, "validate_identity", mismatch)
    response = client.post("/business/verify-identity", json=identity_payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BUSINESS_IDENTITY_MISMATCH"
    assert "verified" not in response.json()
