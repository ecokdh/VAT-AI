import httpx
import pytest

from app.core.config import settings


def response(payload, status_code=200):
    return httpx.Response(status_code, json=payload, request=httpx.Request("POST", settings.NTS_BUSINESS_API_URL))


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setattr(settings, "NTS_BUSINESS_API_KEY", "test-key")


@pytest.mark.parametrize(
    ("code", "name"),
    [("01", "계속사업자"), ("02", "휴업자"), ("03", "폐업자")],
)
def test_status_mapping(client, monkeypatch, code, name):
    def fake_post(url, **kwargs):
        assert url == settings.NTS_BUSINESS_API_URL
        assert kwargs["params"] == {"serviceKey": "test-key"}
        assert kwargs["json"] == {"b_no": ["1234567890"]}
        assert kwargs["timeout"] > 0
        return response({"status_code": "OK", "data": [{
            "b_no": "1234567890", "b_stt": name, "b_stt_cd": code,
            "tax_type": "부가가치세 일반과세자", "tax_type_cd": "01",
            "end_dt": "20200101" if code == "03" else "",
        }]})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = client.post("/business/verify", json={"business_number": "123-45-67890"})
    assert result.status_code == 200
    assert result.json()["business_status"] == name
    assert result.json()["business_status_code"] == code
    assert result.json()["verified"] is True
    assert result.json()["end_date"] == ("20200101" if code == "03" else None)


def test_unregistered(client, monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: response({"status_code": "OK", "data": [{
        "b_no": "1234567890", "b_stt": "", "b_stt_cd": "",
        "tax_type": "국세청에 등록되지 않은 사업자등록번호입니다.", "tax_type_cd": "", "end_dt": "",
    }]}))
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code == 404
    assert result.json()["error"]["code"] == "BUSINESS_NOT_REGISTERED"


def test_missing_key(client, monkeypatch):
    monkeypatch.setattr(settings, "NTS_BUSINESS_API_KEY", "")
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "BUSINESS_API_NOT_CONFIGURED"


def test_timeout(client, monkeypatch):
    def fake_post(*a, **kw):
        raise httpx.ReadTimeout("timeout")
    monkeypatch.setattr(httpx, "post", fake_post)
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code == 504
    assert result.json()["error"]["code"] == "BUSINESS_API_TIMEOUT"


def test_network_error(client, monkeypatch):
    def fake_post(*a, **kw):
        raise httpx.ConnectError("connection failed")
    monkeypatch.setattr(httpx, "post", fake_post)
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "BUSINESS_API_ERROR"


@pytest.mark.parametrize("payload,status", [({"error": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}, 403), ({"error": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}, 429), ({"error": "HTTP_ERROR"}, 500)])
def test_http_errors(client, monkeypatch, payload, status):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: response(payload, status))
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code >= 500
    assert "test-key" not in result.text


@pytest.mark.parametrize("payload", [None, {"status_code": "OK", "data": []}, {"status_code": "OK", "data": [{"b_no": "1234567890", "b_stt": "계속사업자"}]}])
def test_invalid_response(client, monkeypatch, payload):
    if payload is None:
        fake = lambda *a, **kw: httpx.Response(200, content=b"not json", request=httpx.Request("POST", settings.NTS_BUSINESS_API_URL))
    else:
        fake = lambda *a, **kw: response(payload)
    monkeypatch.setattr(httpx, "post", fake)
    result = client.post("/business/verify", json={"business_number": "1234567890"})
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "BUSINESS_API_INVALID_RESPONSE"


@pytest.mark.parametrize("number", ["123", "123456789A", "１２３４５６７８９０"])
def test_format_validation(client, monkeypatch, number):
    def fail(*a, **kw):
        pytest.fail("Invalid input must not call NTS")
    monkeypatch.setattr(httpx, "post", fail)
    result = client.post("/business/verify", json={"business_number": number})
    assert result.status_code == 400
    assert result.json()["error"]["code"] == "VALIDATION_ERROR"
