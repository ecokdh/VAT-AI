from app.receipts.luna_low_contract import normalize, normalize_datetime_string


def _raw(*amounts, vendor="인쇄상호", branch=None, business_number=None, datetime_value=None, items=None):
    return {
        "h": {
            "vendor": vendor,
            "branch": branch,
            "business_number": business_number,
            "datetime": datetime_value,
        },
        "m": list(amounts),
        "i": list(items or []),
        "uncertain": [],
    }


def _amount(role, value, scope="unknown", label=None):
    return {"role": role, "scope": scope, "label": label or role, "value": value}


def test_calculation_and_transaction_save_candidate_do_not_become_printed_fields():
    doc = normalize(_raw(_amount("total", 11000), _amount("vat", 1000)))
    fields = doc["fields"]

    assert fields["printed_total_amount"] == 11000
    assert fields["payment_amount"] is None
    assert fields["supply_amount"] is None
    assert fields["calculated_supply_amount"] == 10000
    assert fields["transaction_save_amount"] == 11000
    assert fields["transaction_save_amount_source"] == "printed_total_amount_fallback"
    assert doc["calculated_values"]["calculated_supply_amount"]["applied_to_extraction"] is False
    assert doc["field_provenance"]["transaction_save_amount"]["applied_to_payment_amount"] is False


def test_computed_total_stays_separate_and_never_fills_storage_candidate():
    doc = normalize(_raw(_amount("supply", 5000), _amount("vat", 500)))
    fields = doc["fields"]

    assert fields["printed_total_amount"] is None
    assert fields["calculated_total_amount"] == 5500
    assert fields["transaction_save_amount"] is None
    assert fields["payment_amount"] is None


def test_negative_zero_and_null_amounts_remain_distinct():
    negative = normalize(_raw(_amount("total", 11000), _amount("payment", -11000)))
    zero = normalize(_raw(_amount("total", 0), _amount("payment", 0)))
    missing = normalize(_raw(_amount("total", None), _amount("payment", None)))

    assert negative["fields"]["payment_amount"] == -11000
    assert negative["fields"]["transaction_save_amount"] == -11000
    assert zero["fields"]["printed_total_amount"] == 0
    assert zero["fields"]["payment_amount"] == 0
    assert missing["fields"]["printed_total_amount"] is None
    assert missing["fields"]["payment_amount"] is None
    assert missing["fields"]["transaction_save_amount"] is None


def test_conflicting_roles_and_mixed_tax_keep_candidates_without_arithmetic_replacement():
    doc = normalize(
        _raw(
            _amount("supply", 5000, "taxable", "과세 공급가액"),
            _amount("supply", 2000, "exempt", "면세 공급가액"),
            _amount("vat", 500, "taxable", "부가세"),
            _amount("exempt", 2000, "exempt", "면세금액"),
            _amount("total", 7500, "all", "합계"),
            _amount("payment", 7500, "unknown", "복합 결제"),
        )
    )
    fields = doc["fields"]

    assert fields["supply_amount"] is None
    assert fields["taxable_supply_amount"] == 5000
    assert fields["printed_total_amount"] == 7500
    assert fields["payment_amount"] == 7500
    assert fields["calculated_supply_amount"] is None
    assert "supply_amount" in doc["conflicts"]
    assert len(fields["conflicting_candidates"]["supply_amount"]) == 2


def test_printed_identity_is_not_replaced_by_merchant_recommendations():
    doc = normalize(
        _raw(
            _amount("total", 55000),
            vendor="입덕농업주유소",
            business_number="311-82-04197",
        )
    )
    fields = doc["fields"]

    assert fields["vendor"] == "입덕농업주유소"
    assert fields["business_number"] == "311-82-04197"
    assert fields["suggested_vendor"] == "합덕농협주유소"
    assert doc["merchant_recommendations"]["vendor"]["origin"] == "external_information_or_merchant_memory"
    assert doc["field_provenance"]["vendor"]["origin"] == "printed_extraction"


def test_dates_format_only_valid_values_and_arbitrary_receipt_values_are_preserved():
    assert normalize_datetime_string("2024년 2월 29일 오후 1:05") == "2024-02-29 13:05"
    assert normalize_datetime_string("2023-02-29 13:05") == "2023-02-29 13:05"
    raw = _raw(
        _amount("total", 812340),
        _amount("payment", 812340),
        vendor="임의 식당 2027",
        branch="별관 2층",
        datetime_value="2027-11-09 08:21:05",
    )

    fields = normalize(raw)["fields"]
    assert fields["vendor"] == "임의 식당 2027"
    assert fields["branch"] == "별관 2층"
    assert fields["printed_total_amount"] == 812340
    assert fields["payment_amount"] == 812340
    assert fields["transaction_datetime"] == "2027-11-09 08:21:05"


def test_item_order_raw_names_and_parent_references_are_retained():
    raw_items = [
        {"n": "옵션 1", "q": 1, "u": 0, "p": 0, "t": "option", "parent": 1},
        {"n": "상품 2", "q": 1, "u": 1200, "p": 1200, "t": "item", "parent": None},
    ]
    items = normalize(_raw(items=raw_items))["items"]

    assert [item["raw_name"] for item in items] == ["옵션 1", "상품 2"]
    assert [item["parent_row"] for item in items] == [1, None]
    assert [item["name"] for item in items] == ["옵션 1", "상품 2"]
