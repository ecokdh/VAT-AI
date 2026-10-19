import uuid
from sqlmodel import Session

from app.business.merchant_memory import (
    clean_biz_number,
    format_biz_number,
    get_merchant_by_biz_no,
    record_merchant,
    resolve_merchant_identity,
)
from app.business.models import MerchantMemory
from app.receipts.luna_low_contract import normalize, validate_nts_checksum, suggest_business_number_repair


def test_merchant_memory_seed_lookup():
    starbucks = get_merchant_by_biz_no("201-81-21515")
    assert starbucks is not None
    assert starbucks["name"] == "STARBUCKS"
    assert starbucks["tax_type"] == "일반과세자"

    korail = get_merchant_by_biz_no("1078657147")
    assert korail is not None
    assert korail["name"] == "코레일유통(주)"

    none_res = get_merchant_by_biz_no("0000000000")
    assert none_res is None


def test_resolve_merchant_identity():
    # 1. Match by business number overrides any OCR noise in vendor
    name, tax_type = resolve_merchant_identity("3118204197", "입덕농업주유소")
    assert name == "합덕농협주유소"
    assert tax_type == "일반과세자"

    # 2. Franchise brand alias fallback when biz number is absent or unseeded
    name, _ = resolve_merchant_identity(None, "스타벅스 강남점")
    assert name == "스타벅스 강남점"

    name, _ = resolve_merchant_identity(None, "emart24")
    assert name == "이마트24"

    name, _ = resolve_merchant_identity(None, "아성다이소")
    assert name == "(주)아성다이소"


def test_record_merchant_memory_dynamic(client):
    override = client.app.dependency_overrides[
        __import__("app.core.database", fromlist=["get_session"]).get_session
    ]
    session = next(override())
    new_biz = "1234567890"
    saved = record_merchant(
        session=session,
        business_number=new_biz,
        business_name="테스트상점",
        branch="본점",
        tax_type="일반과세자",
        source="user_confirmed",
    )
    assert saved is not None
    assert saved.business_number == new_biz
    assert saved.business_name == "테스트상점"

    # Lookup from database
    found = get_merchant_by_biz_no(new_biz, session=session)
    assert found is not None
    assert found["name"] == "테스트상점"
    assert found["branch"] == "본점"


def test_contract_normalization_integration():
    raw_doc = {
        "h": {
            "vendor": "입덕농업주유소",
            "branch": None,
            "business_number": "311-82-04197",
            "datetime": "2026-10-12 12:00:00",
        },
        "m": [
            {"role": "total", "scope": "all", "label": "합계", "value": 55000},
            {"role": "vat", "scope": "taxable", "label": "부가세", "value": 5000},
            {"role": "payment", "scope": "unknown", "label": "카드", "value": 55000},
        ],
        "i": [],
        "uncertain": [],
    }
    normalized = normalize(raw_doc)
    fields = normalized["fields"]

    # Printed extraction stays raw; merchant-memory values remain recommendations.
    assert fields["vendor"] == "입덕농업주유소"
    assert fields["raw_vendor"] == "입덕농업주유소"
    assert fields["suggested_vendor"] == "합덕농협주유소"

    # A calculated supply value is a reference, never an extracted printed amount.
    assert fields["supply_amount"] is None
    assert fields["calculated_supply_amount"] == 50000
    assert fields["vat_amount"] == 5000
    assert fields["payment_amount"] == 55000
    assert normalized["calculated_values"]["calculated_supply_amount"]["applied_to_extraction"] is False
