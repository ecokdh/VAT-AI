# -*- coding: utf-8 -*-
"""
Phase 3 & Step 5: Conditional Routing Rules (Without Ground Truth)
Defines heuristics based strictly on runtime signals:
1. Business number format & checksum failure (advisory only, does not render receipt unsupported)
2. Missing mandatory fields or role candidate conflicts
3. Conditional arithmetic verification (Total vs Supply + VAT, discount handling without double-subtraction)
4. Distinguishes unapplicable arithmetic from passed verification
5. Preserves valid negative/cancellation transactions
6. Aspect ratio and EXIF orientation analysis
"""
from datetime import date
from typing import Any, Dict, List, Optional
import re


def check_business_number_signal(fields: dict) -> dict:
    biz = fields.get("business_number") or fields.get("raw_business_number")
    if not biz:
        return {"suspicious": True, "reason": "business_number_missing", "field": "business_number", "critical": False}
    digits = re.sub(r"\D", "", str(biz))
    if len(digits) != 10:
        return {"suspicious": True, "reason": "business_number_invalid_length", "field": "business_number", "critical": False}

    # NTS Checksum
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    s = sum(int(digits[i]) * weights[i] for i in range(8))
    p = int(digits[8]) * 5
    s += (p // 10) + (p % 10)
    chk = (10 - (s % 10)) % 10
    if int(digits[9]) != chk:
        return {"suspicious": True, "reason": "business_number_checksum_failed", "field": "business_number", "critical": False}
    return {"suspicious": False, "reason": None, "field": "business_number", "critical": False}


def check_amount_arithmetic_signal(fields: dict, conflicts: list) -> list[dict]:
    flags = []
    # 1. Direct conflicts from multiple candidates
    if conflicts:
        for c in conflicts:
            flags.append({
                "suspicious": True,
                "reason": f"candidate_conflict_{c}",
                "field": c,
                "critical": True,
            })

    # 2. Conditional arithmetic verification
    tot = fields.get("printed_total_amount")
    pay = fields.get("payment_amount")
    sup = fields.get("supply_amount")
    vat = fields.get("vat_amount")
    exempt = fields.get("tax_exempt_amount") or 0
    disc = fields.get("discount_amount") or 0

    # Negative transaction check: normal return/refund/cancellation is not an OCR error
    if (pay is not None and pay < 0) or (tot is not None and tot < 0):
        flags.append({
            "suspicious": False,
            "reason": "negative_refund_transaction",
            "field": "payment_amount",
            "is_refund": True,
        })

    # Check Total vs Supply + VAT (ONLY when both supply and vat are explicitly present)
    if tot is not None and sup is not None and vat is not None:
        # Prevent double-subtracting discount:
        # Case A: discount is already factored into supply/vat (tot == sup + vat + exempt)
        # Case B: discount is subtracted from total at end (tot == sup + vat + exempt - disc)
        diff_no_disc = abs(tot - (sup + vat + exempt))
        diff_with_disc = abs(tot - (sup + vat + exempt - disc))

        if min(diff_no_disc, diff_with_disc) > 10:
            flags.append({
                "suspicious": True,
                "reason": f"arithmetic_mismatch_total_vs_components (tot={tot}, sup={sup}, vat={vat}, exempt={exempt}, disc={disc})",
                "field": "amount_group",
                "critical": True,
            })

    # Check VAT approx 10% of taxable supply (only if taxable supply is explicitly labeled and > 100 KRW)
    if sup is not None and vat is not None and sup > 100:
        expected_vat = sup * 0.1
        if abs(vat - expected_vat) > (sup * 0.05 + 10):
            flags.append({
                "suspicious": True,
                "reason": f"vat_rate_mismatch (sup={sup}, vat={vat})",
                "field": "vat_amount",
                "critical": False,
            })

    return flags


def check_mandatory_fields_signal(fields: dict) -> list[dict]:
    flags = []
    if not fields.get("vendor"):
        flags.append({"suspicious": True, "reason": "missing_vendor", "field": "vendor", "critical": True})
    if not fields.get("transaction_datetime"):
        flags.append({"suspicious": True, "reason": "missing_datetime", "field": "transaction_datetime", "critical": True})
    if fields.get("payment_amount") is None and fields.get("printed_total_amount") is None:
        flags.append({"suspicious": True, "reason": "missing_amount", "field": "amount_group", "critical": True})
    return flags


def route_suspicious_fields(norm_result: dict, image_meta: Optional[dict] = None) -> dict:
    fields = norm_result.get("fields", {})
    conflicts = norm_result.get("conflicts", [])
    uncertain = norm_result.get("uncertain", [])

    suspicious_targets = []
    advisory_targets = []

    # 1. Orientation check
    if image_meta and image_meta.get("rotation_applied_deg", 0) > 0:
        advisory_targets.append({
            "target": "full_image_rotation",
            "reason": image_meta.get("reason", "orientation_corrected"),
            "action": "orientation_normalized",
        })

    # 2. Business number check
    biz_res = check_business_number_signal(fields)
    if biz_res["suspicious"]:
        suspicious_targets.append({
            "target": "business_number",
            "reason": biz_res["reason"],
            "suggested_value": fields.get("suggested_business_number"),
            "action": "user_confirm_business_number",
        })

    # 3. Amount checks
    amount_flags = check_amount_arithmetic_signal(fields, conflicts)
    for af in amount_flags:
        if af.get("suspicious"):
            suspicious_targets.append({
                "target": af["field"],
                "reason": af["reason"],
                "action": "user_confirm_amount",
            })
        elif af.get("is_refund"):
            advisory_targets.append({
                "target": "refund_notice",
                "reason": "취소·환불 거래로 감지되었습니다.",
                "action": "preserve_negative_value",
            })

    # 4. Mandatory fields
    mand_flags = check_mandatory_fields_signal(fields)
    for mf in mand_flags:
        suspicious_targets.append({
            "target": mf["field"],
            "reason": mf["reason"],
            "action": "user_input_required",
        })

    # 5. Model-reported uncertainty
    if uncertain:
        for u in uncertain:
            suspicious_targets.append({
                "target": "uncertain_region",
                "reason": f"model_reported_uncertainty: {u}",
                "action": "flag_for_review",
            })

    # Arithmetic applicability
    has_arithmetic_data = (
        fields.get("printed_total_amount") is not None
        and fields.get("supply_amount") is not None
        and fields.get("vat_amount") is not None
    )
    arithmetic_status = (
        "mismatch" if any("arithmetic_mismatch" in t.get("reason", "") for t in suspicious_targets)
        else ("verified" if has_arithmetic_data else "unapplicable")
    )

    return {
        "has_suspicion": len(suspicious_targets) > 0,
        "suspicion_count": len(suspicious_targets),
        "arithmetic_status": arithmetic_status,
        "targets": suspicious_targets,
        "advisory": advisory_targets,
    }


def apply_post_extraction_checks(
    doc: dict,
    orientation_meta: Optional[dict] = None,
    *,
    use_transaction_save_amount: bool = True,
) -> tuple[int | None, date | None, list[str], list[str]]:
    """Run shared routing checks, amount/date validation, and missing-field detection on normalized receipt docs."""
    fields = doc.setdefault("fields", {})
    warnings: list[str] = [
        *doc.get("uncertain", []),
        *("금액 후보 충돌: " + k for k in doc.get("conflicts", [])),
    ]
    routing = route_suspicious_fields(doc, orientation_meta)
    doc["routing"] = routing
    for target in routing.get("targets", []):
        reason = str(target.get("reason", ""))
        if reason == "business_number_checksum_failed":
            warnings.append("사업자번호 체크섬 불일치: 사용자 확인 권장")
        elif "arithmetic_mismatch" in reason:
            warnings.append("금액 구성요소 합산 불일치: 사용자 확인 권장")

    if use_transaction_save_amount:
        # This value is only a transaction-save candidate; keep it separate from printed fields.
        amount = fields.get("transaction_save_amount")
        doc["amount_source"] = fields.get("transaction_save_amount_source")
    else:
        if fields.get("payment_amount") is not None:
            amount = fields["payment_amount"]
            doc["amount_source"] = "payment_amount"
        else:
            amount = fields.get("printed_total_amount")
            doc["amount_source"] = "printed_total_amount" if amount is not None else None

    if amount is not None and (isinstance(amount, bool) or amount < 0 or amount != int(amount)):
        warnings.append("음수·소수 금액은 현재 MVP 정수 거래 계약에서 직접 확정할 수 없습니다. 인쇄값은 상세 결과에 보존했습니다.")
        amount = None
    elif amount is not None:
        amount = int(amount)

    tx_date = None
    match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", str(fields.get("transaction_datetime") or ""))
    if match:
        try:
            tx_date = date(*map(int, match.groups()))
        except ValueError:
            warnings.append("유효하지 않은 거래일입니다.")

    missing = [
        k
        for k, v in [("vendor", fields.get("vendor")), ("amount", amount), ("transaction_date", tx_date)]
        if v is None or v == ""
    ]
    deduped_warnings = list(dict.fromkeys(warnings))
    return amount, tx_date, missing, deduped_warnings
