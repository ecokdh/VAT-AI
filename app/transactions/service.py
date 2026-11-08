import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, select

from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.common.exceptions import AppException
from app.deduction.models import Deduction
from app.deduction.schemas import ReportItem, ReportOut
from app.receipts.models import Receipt
from app.sales_filing import service as sales_filing
from app.vat_return.engine import (
    FIRST_HALF_PERIODS,
    PERIODS,
    RULE_VERSION,
    SECOND_HALF_PERIODS,
    TaxLine,
    calculate_estimate,
    period_bounds,
)
from app.transactions.models import AnalysisRun, FilingInput, Transaction, TransactionRevision
from app.transactions.schemas import AnalysisRunCreate, TransactionCreate, TransactionUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owned(session: Session, user_id: uuid.UUID, transaction_id: int) -> Transaction:
    item = session.exec(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    ).first()
    if item is None:
        raise AppException(404, "NOT_FOUND", "거래를 찾을 수 없습니다.")
    return item


def _snapshot(item: Transaction) -> str:
    values = {
        "revision": item.revision,
        "direction": item.direction,
        "transaction_date": item.transaction_date.isoformat(),
        "vendor": item.vendor,
        "description": item.description,
        "purpose": item.purpose,
        "evidence_type": item.evidence_type,
        "business_related": item.business_related,
        "total_amount": item.total_amount,
        "supply_amount": item.supply_amount,
        "vat_amount": item.vat_amount,
        "deemed_input_supply": item.deemed_input_supply,
        "deemed_input_eligible": item.deemed_input_eligible,
        "deemed_input_document_type": item.deemed_input_document_type,
        "tax_treatment": item.tax_treatment,
    }
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _record_revision(session: Session, item: Transaction) -> None:
    session.add(TransactionRevision(transaction_id=item.id, revision=item.revision, snapshot_json=_snapshot(item)))


def _apply_create(item: Transaction, data: TransactionCreate) -> None:
    for key, value in data.model_dump().items():
        setattr(item, key, value)


def create_transaction(session: Session, user_id: uuid.UUID, data: TransactionCreate) -> Transaction:
    if data.direction == "sales" and data.deemed_input_supply:
        raise AppException(400, "VALIDATION_ERROR", "매출 거래에는 의제매입 정보를 지정할 수 없습니다.")
    item = Transaction(user_id=user_id)
    _apply_create(item, data)
    session.add(item)
    session.flush()
    _record_revision(session, item)
    session.commit()
    session.refresh(item)
    return item


def create_from_receipt(
    session: Session,
    user_id: uuid.UUID,
    receipt_id: int,
    data: TransactionCreate,
) -> Transaction:
    receipt = session.exec(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    if receipt.status != "done":
        raise AppException(409, "OCR_NOT_COMPLETE", "OCR 완료 후 거래를 확인해 주세요.")
    if not receipt.extraction_confirmed:
        raise AppException(409, "EXTRACTION_NOT_CONFIRMED", "보관함으로 이동하기 전에 OCR 추출 내용을 먼저 확인해 주세요.")
    existing = session.exec(select(Transaction).where(Transaction.receipt_id == receipt_id)).first()
    if existing:
        if existing.user_id != user_id:
            raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
        raise AppException(409, "TRANSACTION_EXISTS", "이미 거래로 등록된 영수증입니다.")
    item = Transaction(user_id=user_id, receipt_id=receipt_id)
    item.retention_status = receipt.retention_status
    _apply_create(item, data)
    try: review=(json.loads(receipt.ocr_raw or '{}').get('review') or {})
    except (ValueError,AttributeError): review={}
    item.question_answers_json=json.dumps(review.get('question_answers') or {},ensure_ascii=False)
    item.question_rule_version=review.get('question_version')
    if review.get('question_answers'):
        item.purpose=review.get('purpose');item.business_related=review.get('business_related')
    session.add(item)
    session.flush()
    _record_revision(session, item)
    session.commit()
    session.refresh(item)
    return item


def list_transactions(
    session: Session, user_id: uuid.UUID, direction: str | None = None
) -> list[Transaction]:
    statement = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
    )
    if direction is not None:
        statement = statement.where(Transaction.direction == direction)
    return list(session.exec(statement.order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all())


def list_trash(session: Session, user_id: uuid.UUID) -> list[Transaction]:
    return list(
        session.exec(
            select(Transaction)
            .where(Transaction.user_id == user_id, Transaction.deleted_at.is_not(None))
            .order_by(Transaction.deleted_at.desc(), Transaction.id.desc())
        ).all()
    )


def update_transaction(
    session: Session, user_id: uuid.UUID, transaction_id: int, data: TransactionUpdate
) -> Transaction:
    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is not None:
        raise AppException(409, "TRANSACTION_IN_TRASH", "휴지통에서 복원한 뒤 수정해 주세요.")
    before = _snapshot(item)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    if item.supply_amount is not None and item.supply_amount > item.total_amount:
        raise AppException(400, "VALIDATION_ERROR", "공급가액은 거래 총액보다 클 수 없습니다.")
    if item.vat_amount is not None and item.vat_amount > item.total_amount:
        raise AppException(400, "VALIDATION_ERROR", "부가가치세는 거래 총액보다 클 수 없습니다.")
    if item.supply_amount is not None and item.vat_amount is not None:
        if item.supply_amount + item.vat_amount > item.total_amount:
            raise AppException(400, "VALIDATION_ERROR", "공급가액과 세액의 합은 거래 총액보다 클 수 없습니다.")
    if item.direction == "sales" and item.deemed_input_supply:
        raise AppException(400, "VALIDATION_ERROR", "매출 거래에는 의제매입 정보를 지정할 수 없습니다.")
    if before == _snapshot(item):
        return item
    item.revision += 1
    item.updated_at = _now()
    if item.direction == "purchase":
        # Old analysis belongs to the previous input version and leaves the live estimate now.
        item.review_status = "stale"
        item.risk_level = None
        item.deductible_vat = 0
        item.analysis_reason = None
        item.legal_references_json = "[]"
    session.add(item)
    _record_revision(session, item)
    session.commit()
    session.refresh(item)
    return item


def set_fixed_asset(session: Session, user_id: uuid.UUID, transaction_id: int, value: bool) -> Transaction:
    # 신고서 칸 배정(10 일반매입 ↔ 12 고정자산매입)만 바뀌므로 revision·분석 결과는 건드리지 않는다.
    item = _owned(session, user_id, transaction_id)
    if item.direction != "purchase":
        raise AppException(400, "VALIDATION_ERROR", "고정자산은 매입 거래에만 지정할 수 있습니다.")
    item.is_fixed_asset = value
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


# 예정고지세액은 확정신고(1기·2기)에서만 차감한다.
FINAL_PERIOD = re.compile(r"^\d{4}-H[12]$")


def _filing_period(period: str) -> str:
    if not FINAL_PERIOD.match(period):
        raise AppException(400, "UNSUPPORTED_TAX_PERIOD", "예정고지세액은 확정 신고기간(1기·2기)에만 입력할 수 있습니다.")
    return period


def get_filing_input(session: Session, user_id: uuid.UUID, period: str) -> FilingInput | None:
    return session.exec(select(FilingInput).where(FilingInput.user_id == user_id, FilingInput.period == _filing_period(period))).first()


def save_filing_input(session: Session, user_id: uuid.UUID, period: str, preliminary_notice_tax: int | None) -> FilingInput:
    item = get_filing_input(session, user_id, period) or FilingInput(user_id=user_id, period=period)
    item.preliminary_notice_tax = preliminary_notice_tax
    item.updated_at = _now()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


EDITABLE_DETAILS = {"address", "phone", "payment_method", "approval_number", "receipt_number", "additional_fields"}


def edit_receipt_document(session: Session, user_id: uuid.UUID, transaction_id: int, document, details=None) -> Transaction:
    """보관함 '수정하기': 영수증 확인본(review)과 상세 정보를 고치고 거래 값도 같이 맞춘다."""
    from datetime import date
    from app.receipts.details import project_luna_details

    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is not None:
        raise AppException(409, "TRANSACTION_IN_TRASH", "휴지통에서 복원한 뒤 수정해 주세요.")
    receipt = session.get(Receipt, item.receipt_id) if item.receipt_id else None
    if receipt is None:
        raise AppException(400, "RECEIPT_REQUIRED", "영수증이 연결된 거래만 수정할 수 있습니다.")
    fields = document.fields
    if not (fields.vendor or "").strip():
        raise AppException(400, "VALIDATION_ERROR", "거래처를 입력해 주세요.")
    try:
        transaction_date = date.fromisoformat((fields.transaction_datetime or "")[:10])
    except ValueError:
        raise AppException(400, "VALIDATION_ERROR", "거래일을 확인해 주세요.")
    amounts = {key: getattr(fields, key) for key in ("payment_amount", "supply_amount", "vat_amount")}
    if amounts["payment_amount"] is None or any(v is not None and (v < 0 or int(v) != v) for v in amounts.values()):
        raise AppException(400, "VALIDATION_ERROR", "결제액·공급가액·부가세를 0 이상의 원 단위로 입력해 주세요.")

    corrected = document.model_dump(mode="json")
    try:
        raw = json.loads(receipt.ocr_raw or "{}")
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    review = raw.get("review") or {}
    previous = ((review.get("document") or raw.get("document") or {}).get("fields")) or {}
    sources = review.get("field_sources") or {}
    review.update(document=corrected, saved_at=_now().isoformat(),
                  field_sources={k: "user_edit" if v != previous.get(k) else sources.get(k, "user_confirmed") for k, v in corrected["fields"].items()})
    raw["review"] = review
    receipt.ocr_raw = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    merged = project_luna_details(corrected, receipt.details)
    if details is not None:
        merged.update(details.model_dump(mode="json", include=EDITABLE_DETAILS, exclude_unset=True))
    receipt.details_json = json.dumps(merged, ensure_ascii=False)
    receipt.vendor, receipt.amount, receipt.date = fields.vendor.strip(), amounts["payment_amount"], transaction_date
    session.add(receipt)

    to_int = lambda v: None if v is None else int(v)
    names = ", ".join(i.name for i in document.items if i.row_type == "item")
    updated = update_transaction(session, user_id, transaction_id, TransactionUpdate(
        vendor=fields.vendor.strip(), transaction_date=transaction_date, description=names or item.description,
        total_amount=to_int(amounts["payment_amount"]), supply_amount=to_int(amounts["supply_amount"]), vat_amount=to_int(amounts["vat_amount"]),
    ))
    session.commit()  # 거래 값이 그대로여도 영수증 수정(사업자번호·품목 등)은 저장한다.
    session.refresh(updated)
    return updated


def confirm_transaction(session: Session, user_id: uuid.UUID, transaction_id: int) -> Transaction:
    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is not None:
        raise AppException(409, "TRANSACTION_IN_TRASH", "휴지통에서 복원한 뒤 확정해 주세요.")
    if item.state == "confirmed":
        return item
    if not item.vendor.strip() or item.total_amount < 0:
        raise AppException(422, "CONFIRMATION_INCOMPLETE", "거래처와 거래 금액을 확인해 주세요.")
    item.state = "confirmed"
    item.revision += 1
    item.updated_at = _now()
    session.add(item)
    _record_revision(session, item)
    session.commit()
    session.refresh(item)
    return item


def move_to_trash(session: Session, user_id: uuid.UUID, transaction_id: int) -> Transaction:
    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is None:
        item.state_before_delete = item.state
        item.deleted_at = _now()
        item.state = "deleted"
        item.revision += 1
        item.updated_at = item.deleted_at
        session.add(item)
        _record_revision(session, item)
        session.commit()
        session.refresh(item)
    return item


def restore_from_trash(session: Session, user_id: uuid.UUID, transaction_id: int) -> Transaction:
    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is None:
        return item
    item.deleted_at = None
    item.state = item.state_before_delete or "draft"
    item.state_before_delete = None
    item.permanent_delete_requested_at = None
    item.revision += 1
    item.updated_at = _now()
    # A restored purchase must be analyzed again before deductions return to totals.
    if item.direction == "purchase":
        item.review_status = "stale"
        item.risk_level = None
        item.deductible_vat = 0
    session.add(item)
    _record_revision(session, item)
    session.commit()
    session.refresh(item)
    return item


def delete_permanently(session: Session, user_id: uuid.UUID, transaction_id: int) -> None:
    """휴지통에 있는 거래와 연결된 영수증·공제 판별·원본 사진을 지운다. 되돌릴 수 없고, 필요하면 다시 촬영한다."""
    from app.receipts import service as receipt_service

    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is None:
        raise AppException(409, "TRANSACTION_NOT_IN_TRASH", "영구 삭제 전에 휴지통으로 이동해 주세요.")
    receipt = session.get(Receipt, item.receipt_id) if item.receipt_id else None
    for revision in session.exec(select(TransactionRevision).where(TransactionRevision.transaction_id == item.id)).all():
        session.delete(revision)
    session.delete(item)
    session.flush()  # 영수증을 가리키는 거래부터 지운다.
    if receipt:
        for deduction in session.exec(select(Deduction).where(Deduction.receipt_id == receipt.id)).all():
            session.delete(deduction)
        session.delete(receipt)
    session.commit()
    if receipt:
        receipt_service._delete_after_failure(receipt.image_url)  # 사진 정리는 best effort


def create_analysis_run(
    session: Session, user_id: uuid.UUID, data: AnalysisRunCreate
) -> AnalysisRun:
    transaction_ids = list(dict.fromkeys(data.transaction_ids))
    rows = list(
        session.exec(
            select(Transaction).where(
                Transaction.id.in_(transaction_ids),
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        ).all()
    )
    if len(rows) != len(transaction_ids):
        raise AppException(404, "NOT_FOUND", "선택한 거래를 찾을 수 없습니다.")
    not_ready = [row.id for row in rows if row.direction != "purchase" or row.state != "confirmed"]
    if not_ready:
        raise AppException(409, "ANALYSIS_PRECONDITION_FAILED", "확정된 매입 거래만 분석할 수 있습니다.")
    # Pin the input revision at enqueue time. A worker must never publish a result
    # against a transaction that the user edited while analysis was running.
    selected = [{"id": row.id, "revision": row.revision} for row in rows]
    run = AnalysisRun(user_id=user_id, transaction_ids_json=json.dumps(selected))
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_analysis_run(session: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AnalysisRun:
    run = session.exec(select(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.user_id == user_id)).first()
    if run is None:
        raise AppException(404, "NOT_FOUND", "분석 작업을 찾을 수 없습니다.")
    return run


def cancel_analysis_run(session: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AnalysisRun:
    # 대기·진행 중인 작업만 중단한다. 이미 끝난 작업은 그대로 돌려준다.
    # 진행 중이던 작업은 워커가 상태를 확인해 결과를 반영하지 않고 멈춘다.
    # 조건부 UPDATE라서 워커가 막 완료한 작업을 CANCELLED로 덮어쓰지 않는다.
    run = get_analysis_run(session, user_id, run_id)
    session.execute(
        update(AnalysisRun)
        .where(AnalysisRun.id == run.id, AnalysisRun.status.in_(("PENDING", "PROCESSING")))
        .values(status="CANCELLED", finished_at=datetime.now(timezone.utc))
    )
    session.commit()
    session.refresh(run)
    return run


def period_transactions(session: Session, user_id: uuid.UUID, start, end, tax_profile: TaxProfileV2 | None) -> list[Transaction]:
    """세액 계산·신고서가 함께 쓰는 확정 매입 거래.

    매출 거래와 POS 월정산은 여기서 합산하지 않는다. 신고 매출은 sales_filing의
    기간별 확정 집계 한 곳에서만 가져온다.
    """
    rows = list(
        session.exec(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.direction == "purchase",
                Transaction.state == "confirmed",
                Transaction.deleted_at.is_(None),
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
        ).all()
    )
    if tax_profile and tax_profile.business_start_date:
        rows = [row for row in rows if row.transaction_date >= tax_profile.business_start_date]
    if tax_profile and tax_profile.business_end_date:
        rows = [row for row in rows if row.transaction_date <= tax_profile.business_end_date]
    return rows


def calculate_period_estimate(
    session: Session,
    user: User,
    period: str,
    simplified_industry_rate: int | None,
):
    profile = session.exec(select(BusinessProfile).where(BusinessProfile.user_id == user.id)).first()
    tax_type_code = profile.tax_type_code if profile else None
    if tax_type_code not in {"01", "02"}:
        raise AppException(409, "TAX_TYPE_UNAVAILABLE", "국세청 과세유형 조회가 필요합니다.")
    tax_type = "general" if tax_type_code == "01" else "simplified"
    if period.startswith("2025-"):
        from app.jobs.readiness import filter_bounds
        filter_bounds(period)
        return {"period": period, "tax_type": tax_type, "status": "UNAVAILABLE", "output_vat": None,
                "eligible_input_vat": None, "deemed_input_vat": None, "payable_estimate": None,
                "included_transaction_count": 0, "caution_transaction_count": 0, "uncalculated_transaction_count": 0,
                "rule_version": RULE_VERSION, "notes": ["2025년 거래를 조회할 수 있습니다. 현재 계산 규칙은 2026년 전용이므로 2025년 예상세액과 PDF 생성은 제공하지 않습니다."],
                "sales_aggregate_id": None, "sales_aggregate_status": None, "sales_aggregate": None, "draft": True}
    tax_profile = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user.id)).first()
    if tax_profile and tax_profile.tax_type_change_date:
        change_date = tax_profile.tax_type_change_date
        if period not in PERIODS:
            raise AppException(400, "UNSUPPORTED_TAX_PERIOD", "2026년 신고 기간만 지원합니다.")
        range_start, range_end = PERIODS[period]
        if range_start < change_date < range_end:
            return {
                "period": period,
                "tax_type": tax_type,
                "status": "UNAVAILABLE",
                "output_vat": None,
                "eligible_input_vat": None,
                "deemed_input_vat": None,
                "payable_estimate": None,
                "included_transaction_count": 0,
                "caution_transaction_count": 0,
                "uncalculated_transaction_count": 0,
                "rule_version": RULE_VERSION,
                "notes": ["과세기간 중 과세유형이 변경되어 적용 시점별 규칙 검토가 필요합니다. 자동 계산을 보류했습니다."],
                "sales_aggregate_id": None,
                "sales_aggregate_status": None,
                "sales_aggregate": None,
                "draft": True,
            }
        if change_date >= range_end and tax_profile.changed_to_tax_type:
            tax_type = "general" if tax_profile.changed_to_tax_type == "simplified" else "simplified"
        elif change_date <= range_start and tax_profile.changed_to_tax_type:
            tax_type = "general" if tax_profile.changed_to_tax_type == "general" else "simplified"
    if tax_type != "general":
        # Simplified taxation is outside this sales aggregation's supported scope.
        try:
            period_bounds(period, "simplified")
        except ValueError as exc:
            raise AppException(400, "UNSUPPORTED_TAX_PERIOD", str(exc)) from exc
        return {
            "period": period, "tax_type": tax_type, "status": "UNAVAILABLE", "output_vat": None,
            "eligible_input_vat": None, "deemed_input_vat": None, "payable_estimate": None,
            "included_transaction_count": 0, "caution_transaction_count": 0, "uncalculated_transaction_count": 0,
            "rule_version": RULE_VERSION, "notes": ["매출 집계는 일반과세자 1사업장만 지원합니다. 간이과세 신고는 검토가 필요합니다."],
            "sales_aggregate_id": None, "sales_aggregate_status": "검토 필요", "sales_aggregate": None, "draft": True,
        }
    try:
        start, end = period_bounds(period, tax_type)
    except ValueError as exc:
        raise AppException(400, "UNSUPPORTED_TAX_PERIOD", str(exc)) from exc
    rows = period_transactions(session, user.id, start, end, tax_profile)
    sales_case = sales_filing.refresh(session, user, period)
    sales_aggregate = json.loads(sales_case.aggregate_json or "{}")
    sales_lines: list[TaxLine] = []
    if sales_case.status == "확정":
        for line_number, evidence_type in ((1, "tax_invoice"), (3, "card_receipt"), (4, "other")):
            amounts = sales_aggregate.get("lines", {}).get(str(line_number), {})
            if not amounts or not amounts.get("supply_amount"):
                continue
            sales_lines.append(TaxLine(
                direction="sales", state="confirmed", review_status="analyzed", risk_level="SAFE",
                transaction_date=start, total_amount=amounts["total_amount"],
                supply_amount=amounts["supply_amount"], vat_amount=amounts["vat_amount"],
                tax_treatment="standard", evidence_type=evidence_type,
            ))
    deemed_sales_fact = None
    if tax_profile and tax_profile.confirmed_at:
        deemed_sales_fact = tax_profile.deemed_related_taxable_sales_h1 if period in FIRST_HALF_PERIODS else tax_profile.deemed_related_taxable_sales_h2 if period in SECOND_HALF_PERIODS else None
    if tax_type == "simplified" and tax_profile:
        simplified_industry_rate = tax_profile.simplified_industry_rate
    estimate = calculate_estimate(
        tax_type=tax_type,
        period=period,
        simplified_industry_rate=simplified_industry_rate,
        entity_type=tax_profile.entity_type if tax_profile and tax_profile.confirmed_at else None,
        industry_category=tax_profile.industry_category if tax_profile and tax_profile.confirmed_at else None,
        industry_subtype=tax_profile.industry_subtype if tax_profile and tax_profile.confirmed_at else None,
        is_sme=tax_profile.is_sme if tax_profile and tax_profile.confirmed_at else None,
        deemed_related_taxable_sales=deemed_sales_fact,
        lines=[
            TaxLine(
                direction=row.direction,
                state=row.state,
                review_status=row.review_status,
                risk_level=row.risk_level,
                transaction_date=row.transaction_date,
                total_amount=row.total_amount,
                supply_amount=row.supply_amount,
                vat_amount=row.vat_amount,
                tax_treatment=row.tax_treatment,
                evidence_type=row.evidence_type,
                deemed_input_supply=row.deemed_input_supply,
                business_related=row.business_related,
                deemed_input_eligible=row.deemed_input_eligible,
                deemed_input_document_type=row.deemed_input_document_type,
            )
            for row in rows
        ] + sales_lines,
    )
    notes = list(estimate.notes)
    if sales_case.status != "확정":
        questions = json.loads(sales_case.issues_json or "[]")
        notes.append(f"신고용 매출 집계가 {sales_case.status} 상태입니다. 확인 전에는 매출세액과 납부 예상액을 표시하지 않습니다.")
        notes.extend(item["question"] for item in questions[:5])
    if tax_profile and tax_profile.confirmed_at and tax_profile.suspension_periods_json != "[]":
        suspensions = json.loads(tax_profile.suspension_periods_json)
        if any(
            any(period_start <= row.transaction_date.isoformat() <= period_end for row in rows)
            for period_start, period_end in ((item["start_date"], item["end_date"]) for item in suspensions)
        ):
            notes.append("휴업기간 중 거래가 포함되어 있습니다. 휴업 여부만으로 일괄 제외하지 않고 거래별 사업 관련성과 증빙을 확인해야 합니다.")
    return {
        "period": period,
        "tax_type": tax_type,
        "status": estimate.status if sales_case.status == "확정" else "UNAVAILABLE",
        "output_vat": estimate.output_vat if sales_case.status == "확정" else None,
        "eligible_input_vat": estimate.eligible_input_vat,
        "deemed_input_vat": estimate.deemed_input_vat,
        "payable_estimate": estimate.payable_estimate if sales_case.status == "확정" else None,
        "included_transaction_count": estimate.included_transaction_count,
        "caution_transaction_count": estimate.caution_transaction_count,
        "uncalculated_transaction_count": estimate.uncalculated_transaction_count,
        "rule_version": RULE_VERSION,
        "notes": notes,
        "sales_aggregate_id": sales_case.id,
        "sales_aggregate_status": sales_case.status,
        "sales_aggregate": {
            "revision": sales_case.revision,
            "input_fingerprint": sales_case.input_fingerprint,
            "lines": sales_aggregate.get("lines", {}),
            "deduplicated_rows": sales_aggregate.get("deduplicated_rows", []),
        },
        "draft": sales_case.status != "확정",
    }
