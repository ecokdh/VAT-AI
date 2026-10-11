from io import BytesIO

import pytest
from PIL import Image

from app.auth import service as auth_service
from app.business.schemas import BusinessVerifyResponse


@pytest.fixture(autouse=True)
def verification(monkeypatch):
    monkeypatch.setattr(auth_service, "verify_business", lambda _: BusinessVerifyResponse(
        business_number="1234567890", business_status="계속사업자", business_status_code="01",
        tax_type="부가가치세 일반과세자", tax_type_code="01", verified=True,
    ))


def headers(client, email="qa@example.com"):
    result = client.post("/auth/register", json={
        "email": email, "password": "Qa-only-2026!", "name": "QA", "business_name": "QA",
        "business_number": "1234567890", "terms_accepted": True, "privacy_accepted": True,
    })
    assert result.status_code == 201
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def png():
    output = BytesIO()
    Image.new("RGB", (10, 20), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("direction", ["purchase", "sales"])
def test_capture_direction_and_private_preview(client, direction):
    owner = headers(client)
    content = png()
    created = client.post("/v2/receipt-jobs", headers=owner, data={"direction": direction},
                          files={"file": ("qa.png", content, "image/png")})
    assert created.status_code == 202
    receipt_id = created.json()["receipt_id"]
    detail = client.get(f"/v2/receipts/{receipt_id}", headers=owner)
    assert detail.json()["direction"] == direction
    image = client.get(f"/v2/receipts/{receipt_id}/image", headers=owner)
    assert image.content == content
    assert image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "private, no-store"
    other = headers(client, "other@example.com")
    assert client.get(f"/v2/receipts/{receipt_id}/image", headers=other).status_code == 404
    assert client.get(f"/v2/receipts/{receipt_id}/image").status_code == 401


def test_capture_rejects_unknown_direction(client):
    result = client.post("/v2/receipt-jobs", headers=headers(client), data={"direction": "other"},
                         files={"file": ("qa.png", png(), "image/png")})
    assert result.status_code == 400


def test_capture_keeps_purchase_default_for_existing_clients(client):
    owner = headers(client)
    result = client.post("/v2/receipt-jobs", headers=owner, files={"file": ("qa.png", png(), "image/png")})
    assert result.status_code == 202
    assert client.get(f"/v2/receipts/{result.json()['receipt_id']}", headers=owner).json()["direction"] == "purchase"
