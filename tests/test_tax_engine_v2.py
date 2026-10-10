from datetime import date

import pytest

from app.tax_engine.engine import TaxLine, calculate_estimate, period_bounds


def line(**overrides):
    values = {
        "direction": "purchase",
        "state": "confirmed",
        "review_status": "analyzed",
        "risk_level": "SAFE",
        "transaction_date": date(2026, 3, 1),
        "total_amount": 1100,
        "supply_amount": 1000,
        "vat_amount": 100,
        "tax_treatment": "standard",
        "evidence_type": "tax_invoice",
    }
    values.update(overrides)
    return TaxLine(**values)


def test_2026_tax_periods_are_limited_by_tax_type():
    assert period_bounds("2026-H1", "general") == (date(2026, 1, 1), date(2026, 7, 1))
    assert period_bounds("2026-H2", "general") == (date(2026, 7, 1), date(2027, 1, 1))
    assert period_bounds("2026-YEAR", "simplified") == (date(2026, 1, 1), date(2027, 1, 1))
    with pytest.raises(ValueError):
        period_bounds("2026-YEAR", "general")


def test_general_estimate_excludes_caution_and_stale_purchase_vat():
    estimate = calculate_estimate(
        tax_type="general",
        period="2026-H1",
        lines=[
            line(),
            line(review_status="caution", risk_level="CAUTION", transaction_date=date(2026, 5, 1)),
            line(review_status="stale", risk_level=None, transaction_date=date(2026, 5, 1)),
            line(transaction_date=date(2026, 8, 1)),
        ],
    )
    assert estimate.eligible_input_vat == 100
    assert estimate.caution_transaction_count == 2
    assert estimate.included_transaction_count == 1
    assert estimate.status == "PARTIAL"


def test_information_shortage_is_not_guessed_into_calculation():
    estimate = calculate_estimate(
        tax_type="general",
        period="2026-H1",
        lines=[line(vat_amount=None)],
    )
    assert estimate.eligible_input_vat == 0
    assert estimate.uncalculated_transaction_count == 1
    assert estimate.status == "PARTIAL"


def test_simplified_estimate_requires_verified_industry_rate_and_caps_credit():
    line_item = line(direction="sales", total_amount=1_100_000, supply_amount=1_000_000, vat_amount=100_000)
    unavailable = calculate_estimate(tax_type="simplified", period="2026-YEAR", lines=[line_item])
    assert unavailable.status == "UNAVAILABLE"
    estimate = calculate_estimate(
        tax_type="simplified",
        period="2026-YEAR",
        simplified_industry_rate=20,
        lines=[line_item, line(total_amount=2_200_000, vat_amount=200_000)],
    )
    assert estimate.output_vat == 20_000
    assert estimate.eligible_input_vat == 11_000
    assert estimate.payable_estimate == 9_000


def test_general_restaurant_deemed_input_uses_2026_rate_and_period_cap():
    eligible = line(
        total_amount=1_000_000,
        supply_amount=1_000_000,
        vat_amount=0,
        tax_treatment="exempt",
        evidence_type="tax_free_receipt",
        deemed_input_supply=1_000_000,
        deemed_input_eligible=True,
        deemed_input_document_type="purchase_invoice",
    )
    estimate = calculate_estimate(
        tax_type="general",
        period="2026-H1",
        lines=[eligible],
        entity_type="individual",
        industry_category="food_service",
        industry_subtype="restaurant",
        deemed_related_taxable_sales=1_000_000,
    )
    assert estimate.deemed_input_vat == 61_926  # 75% sales cap, then 9/109 credit rate
    assert estimate.status == "COMPLETE"
    assert any("부가가치세법 제42조" in note for note in estimate.notes)


def test_simplified_taxpayer_does_not_receive_deemed_input_credit():
    eligible = line(
        total_amount=1_000_000,
        supply_amount=1_000_000,
        vat_amount=0,
        tax_treatment="exempt",
        evidence_type="tax_free_receipt",
        deemed_input_supply=1_000_000,
        deemed_input_eligible=True,
        deemed_input_document_type="purchase_invoice",
    )
    estimate = calculate_estimate(
        tax_type="simplified",
        period="2026-YEAR",
        simplified_industry_rate=20,
        lines=[eligible],
    )
    assert estimate.deemed_input_vat == 0
    assert estimate.eligible_input_vat == 0
    assert any("간이과세자는 현행 규정상" in note for note in estimate.notes)


def test_deemed_input_requires_related_taxable_sales_not_total_sales():
    eligible = line(
        total_amount=1_000_000,
        supply_amount=1_000_000,
        vat_amount=0,
        tax_treatment="exempt",
        evidence_type="tax_free_receipt",
        deemed_input_supply=1_000_000,
        deemed_input_eligible=True,
        deemed_input_document_type="purchase_invoice",
    )
    estimate = calculate_estimate(
        tax_type="general",
        period="2026-H1",
        lines=[eligible],
        entity_type="individual",
        industry_category="food_service",
        industry_subtype="restaurant",
        deemed_related_taxable_sales=None,
    )
    assert estimate.deemed_input_vat == 0
    assert estimate.uncalculated_transaction_count == 1
    assert estimate.status == "PARTIAL"


def test_manufacturing_second_period_deemed_credit_is_held_for_annual_adjustment_review():
    eligible = line(
        transaction_date=date(2026, 8, 1),
        total_amount=1_000_000,
        supply_amount=1_000_000,
        vat_amount=0,
        tax_treatment="exempt",
        evidence_type="tax_free_receipt",
        deemed_input_supply=1_000_000,
        deemed_input_eligible=True,
        deemed_input_document_type="farmer_direct",
    )
    estimate = calculate_estimate(
        tax_type="general",
        period="2026-H2",
        lines=[eligible],
        entity_type="individual",
        industry_category="manufacturing",
        industry_subtype="other",
        deemed_related_taxable_sales=1_000_000,
    )
    assert estimate.deemed_input_vat == 0
    assert estimate.uncalculated_transaction_count == 1
    assert any("연간 합산 조정" in note for note in estimate.notes)
