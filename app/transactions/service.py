import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.common.exceptions import AppException
from app.deduction.schemas import ReportItem, ReportOut
from app.receipts.models import Receipt
from app.tax_engine.engine import TaxLine, calculate_estimate, period_bounds, RULE_VERSION
from app.transactions.models import AnalysisRun, Transaction, TransactionRevision
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


def request_permanent_delete(session: Session, user_id: uuid.UUID, transaction_id: int) -> Transaction:
    item = _owned(session, user_id, transaction_id)
    if item.deleted_at is None:
        raise AppException(409, "TRANSACTION_NOT_IN_TRASH", "영구 삭제 요청 전에 휴지통으로 이동해 주세요.")
    if item.retention_status == "required":
        raise AppException(409, "RETENTION_PERIOD_ACTIVE", "법적 보존 기간이 남아 있어 영구 삭제할 수 없습니다.")
    if item.retention_status != "not_required":
        raise AppException(409, "RETENTION_STATUS_UNCONFIRMED", "증빙의 보존 의무를 확인할 수 없어 영구 삭제할 수 없습니다.")
    # This endpoint records a request for the retention review process. It does
    # not physically erase the linked legacy receipt or its source file.
    if item.permanent_delete_requested_at is None:
        item.permanent_delete_requested_at = _now()
        session.add(item)
        session.commit()
        session.refresh(item)
    return item


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
    tax_profile = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user.id)).first()
    if tax_profile and tax_profile.tax_type_change_date:
        change_date = tax_profile.tax_type_change_date
        if period == "2026-H1":
            range_start, range_end = date(2026, 1, 1), date(2026, 7, 1)
        elif period == "2026-H2":
            range_start, range_end = date(2026, 7, 1), date(2027, 1, 1)
        elif period == "2026-YEAR":
            range_start, range_end = date(2026, 1, 1), date(2027, 1, 1)
        else:
            raise AppException(400, "UNSUPPORTED_TAX_PERIOD", "2026년 신고 기간만 지원합니다.")
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
            }
        if change_date >= range_end and tax_profile.changed_to_tax_type:
            tax_type = "general" if tax_profile.changed_to_tax_type == "simplified" else "simplified"
        elif change_date <= range_start and tax_profile.changed_to_tax_type:
            tax_type = "general" if tax_profile.changed_to_tax_type == "general" else "simplified"
    try:
        start, end = period_bounds(period, tax_type)
    except ValueError as exc:
        raise AppException(400, "UNSUPPORTED_TAX_PERIOD", str(exc)) from exc
    rows = list(
        session.exec(
            select(Transaction).where(
                Transaction.user_id == user.id,
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
    deemed_sales_fact = None
    if tax_profile and tax_profile.confirmed_at:
        deemed_sales_fact = tax_profile.deemed_related_taxable_sales_h1 if period == "2026-H1" else tax_profile.deemed_related_taxable_sales_h2 if period == "2026-H2" else None
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
        ],
    )
    notes = list(estimate.notes)
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
        "status": estimate.status,
        "output_vat": estimate.output_vat,
        "eligible_input_vat": estimate.eligible_input_vat,
        "deemed_input_vat": estimate.deemed_input_vat,
        "payable_estimate": estimate.payable_estimate,
        "included_transaction_count": estimate.included_transaction_count,
        "caution_transaction_count": estimate.caution_transaction_count,
        "uncalculated_transaction_count": estimate.uncalculated_transaction_count,
        "rule_version": RULE_VERSION,
        "notes": notes,
    }
