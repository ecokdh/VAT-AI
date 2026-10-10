from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal


RULE_VERSION = "KR-VAT-2026-v1"
STANDARD_RATE = 10
SIMPLIFIED_INPUT_CREDIT_RATE_PER_10000 = 50  # 0.5%


@dataclass(frozen=True)
class TaxLine:
    direction: Literal["purchase", "sales"]
    state: str
    review_status: str
    risk_level: str | None
    transaction_date: date
    total_amount: int
    supply_amount: int | None
    vat_amount: int | None
    tax_treatment: str
    evidence_type: str
    deemed_input_supply: int = 0
    business_related: bool | None = None
    deemed_input_eligible: bool | None = None
    deemed_input_document_type: str | None = None


@dataclass(frozen=True)
class TaxEstimate:
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    output_vat: int | None
    eligible_input_vat: int | None
    deemed_input_vat: int | None
    payable_estimate: int | None
    included_transaction_count: int
    caution_transaction_count: int
    uncalculated_transaction_count: int
    notes: tuple[str, ...]


def period_bounds(period: str, tax_type: str) -> tuple[date, date]:
    if period == "2026-H1" and tax_type == "general":
        return date(2026, 1, 1), date(2026, 7, 1)
    if period == "2026-H2" and tax_type == "general":
        return date(2026, 7, 1), date(2027, 1, 1)
    if period == "2026-YEAR" and tax_type == "simplified":
        return date(2026, 1, 1), date(2027, 1, 1)
    raise ValueError("과세유형과 신고기간 조합을 지원하지 않습니다.")


def _standard_output_vat(line: TaxLine) -> int | None:
    if line.tax_treatment in {"zero", "exempt"}:
        return 0
    if line.tax_treatment != "standard" or line.supply_amount is None:
        return None
    # All values are whole won. Per line, 10% VAT is exact for integer supplies.
    return line.supply_amount * STANDARD_RATE // 100


def calculate_estimate(
    *,
    tax_type: str,
    period: str,
    lines: Iterable[TaxLine],
    simplified_industry_rate: int | None = None,
    entity_type: str | None = None,
    industry_category: str | None = None,
    industry_subtype: str | None = None,
    is_sme: bool | None = None,
    deemed_related_taxable_sales: int | None = None,
) -> TaxEstimate:
    start, end = period_bounds(period, tax_type)
    selected = [line for line in lines if start <= line.transaction_date < end and line.state == "confirmed"]
    notes: list[str] = []
    output_vat = 0
    input_vat = 0
    deemed_input_vat = 0
    included = 0
    caution = 0
    uncalculated = 0
    deemed_supplies = 0
    deemed_pending = 0
    deemed_candidate_count = 0
    deemed_ready_count = 0
    simplified_deemed_count = 0

    if tax_type == "simplified" and simplified_industry_rate not in {15, 20, 25, 30, 40}:
        return TaxEstimate("UNAVAILABLE", None, None, None, None, 0, 0, len(selected), ("국세청 과세유형과 확인된 업종별 부가가치율이 필요합니다.",))

    for line in selected:
        if line.direction == "sales":
            if tax_type == "general":
                amount = _standard_output_vat(line)
                if amount is None:
                    uncalculated += 1
                    continue
                output_vat += amount
            else:
                if line.tax_treatment == "exempt":
                    amount = 0
                elif line.tax_treatment == "standard" and line.supply_amount is not None:
                    amount = line.supply_amount * int(simplified_industry_rate) * STANDARD_RATE // 10_000
                else:
                    uncalculated += 1
                    continue
                output_vat += amount
            included += 1
            continue

        if line.direction != "purchase":
            uncalculated += 1
            continue
        if line.review_status == "excluded":
            # A model's explicit non-deductible classification excludes the item
            # from the credit total without treating it as an unresolved case.
            continue
        if line.business_related is False:
            # User-confirmed personal expenses are excluded from deductible VAT.
            continue
        if line.review_status == "insufficient_info":
            uncalculated += 1
            continue
        if line.review_status in {"caution", "stale", "not_analyzed"} or line.risk_level == "CAUTION":
            caution += 1
            continue
        if line.review_status != "analyzed" or line.risk_level != "SAFE":
            uncalculated += 1
            continue
        if line.tax_treatment == "unknown" or line.evidence_type == "unknown":
            uncalculated += 1
            continue

        if tax_type == "general":
            if line.tax_treatment == "standard":
                if line.vat_amount is None:
                    uncalculated += 1
                    continue
                input_vat += line.vat_amount
            elif line.tax_treatment == "exempt" and line.deemed_input_supply > 0:
                deemed_candidate_count += 1
                if line.deemed_input_eligible is False:
                    included += 1
                    continue
                if line.deemed_input_eligible is not True or not line.deemed_input_document_type:
                    deemed_pending += 1
                    continue
                deemed_supplies += line.deemed_input_supply
                deemed_ready_count += 1
                included += 1
                continue
            elif line.tax_treatment == "zero":
                pass
            else:
                uncalculated += 1
                continue
        else:
            # The simplified taxpayer deemed-input credit (former VAT Act Art. 65)
            # was repealed. Exempt produce purchases cannot receive that credit.
            if line.evidence_type not in {"tax_invoice", "card_receipt"}:
                if line.tax_treatment == "exempt" and line.deemed_input_supply > 0:
                    simplified_deemed_count += 1
                    included += 1
                    continue
                uncalculated += 1
                continue
            input_vat += line.total_amount * SIMPLIFIED_INPUT_CREDIT_RATE_PER_10000 // 10_000
        included += 1

    if tax_type == "general" and deemed_candidate_count:
        if deemed_pending:
            uncalculated += deemed_pending
            notes.append("의제매입 대상 품목·과세사업 사용·증빙 유형을 확인하지 않은 거래는 계산에서 제외했습니다.")
        if deemed_supplies:
            rate: tuple[int, int] | None = None
            if period == "2026-H2" and industry_category == "manufacturing":
                uncalculated += deemed_ready_count
                notes.append("제조업의 2기 의제매입은 연간 합산 조정 요건을 확인해야 하므로 자동 계산을 보류했습니다.")
            elif entity_type not in {"individual", "corporation"} or deemed_related_taxable_sales is None or industry_category not in {"food_service", "manufacturing", "other"}:
                uncalculated += deemed_ready_count
                notes.append("사업자 형태·업종·의제매입 관련 과세 매출 확인이 필요합니다.")
            else:
                if industry_category == "food_service" and industry_subtype == "taxable_entertainment":
                    rate = (2, 102)
                elif industry_category == "food_service" and entity_type == "individual":
                    rate = (9, 109) if deemed_related_taxable_sales <= 200_000_000 else (8, 108)
                elif industry_category == "food_service":
                    rate = (6, 106)
                elif industry_category == "manufacturing" and industry_subtype == "specified_mill" and entity_type == "individual":
                    rate = (6, 106)
                elif industry_category == "manufacturing" and (entity_type == "individual" or is_sme is True):
                    rate = (4, 104)
                elif industry_category == "manufacturing" and entity_type == "corporation" and is_sme is None:
                    uncalculated += deemed_ready_count
                    notes.append("제조업 법인의 중소기업 해당 여부를 확인해야 합니다.")
                else:
                    rate = (2, 102)

                if rate is not None:
                    if entity_type == "corporation":
                        cap_percent = 50
                    elif industry_category == "food_service":
                        cap_percent = 75 if deemed_related_taxable_sales <= 100_000_000 else 70 if deemed_related_taxable_sales <= 200_000_000 else 60
                    else:
                        cap_percent = 65 if deemed_related_taxable_sales <= 200_000_000 else 55
                    capped_supply = min(deemed_supplies, deemed_related_taxable_sales * cap_percent // 100)
                    deemed_input_vat = capped_supply * rate[0] // rate[1]
                    notes.append(f"의제매입세액은 과세기간 관련 매출 한도({cap_percent}%)와 확인된 업종 공제율을 적용했습니다. (부가가치세법 제42조, 시행령 제84조)")
        if deemed_candidate_count and not deemed_input_vat and not deemed_pending:
            notes.append("해당 과세기간의 의제매입 공제 계산 결과가 0원입니다.")

    if simplified_deemed_count:
        notes.append("간이과세자는 현행 규정상 의제매입세액공제를 적용하지 않습니다.")

    if tax_type == "simplified" and input_vat > output_vat:
        notes.append("간이과세자는 공제액이 납부세액을 초과하는 부분을 환급으로 계산하지 않습니다.")
    payable = max(0, output_vat - input_vat - deemed_input_vat)
    if caution:
        notes.append("CAUTION 및 검토 중인 매입은 공제액에서 제외했습니다.")
    if uncalculated:
        notes.append("정보가 부족하거나 지원 규칙 검증이 필요한 거래는 계산에서 제외했습니다.")
    status = "PARTIAL" if caution or uncalculated else "COMPLETE"
    return TaxEstimate(status, output_vat, input_vat, deemed_input_vat, payable, included, caution, uncalculated, tuple(notes))
