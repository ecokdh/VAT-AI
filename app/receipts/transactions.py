"""Confirmed document facts, evidence links and explicit reconciliation decisions."""
from datetime import date
import json
import uuid
from typing import Literal, Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from sqlalchemy import update as sa_update, case
from sqlmodel import Session, select

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.common.exceptions import AppException
from app.core.database import get_session
from app.receipts.document import DocumentFacts, StructuredItem
from app.receipts.models import Receipt, LineItem, Transaction, ReconciliationIssue
from app.receipts.schemas import ReceiptOut

router = APIRouter(tags=["transactions"])


def owned_transaction(session: Session, user_id: uuid.UUID, transaction_id: str) -> Transaction:
    transaction = session.exec(select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)).first()
    if transaction is None:
        raise AppException(404, "NOT_FOUND", "거래를 찾을 수 없습니다.")
    return transaction


def transaction_receipts(session: Session, user_id: uuid.UUID, transaction_id: str) -> list[Receipt]:
    return list(session.exec(select(Receipt).where(Receipt.transaction_id == transaction_id, Receipt.user_id == user_id).order_by(Receipt.id)).all())


def create_from_receipt(session: Session, receipt: Receipt) -> Transaction:
    facts = ReceiptOut.model_validate(receipt)
    document = facts.document
    transaction = Transaction(user_id=receipt.user_id, adjustment_type=document.adjustment_type,
        workflow_status="UNRESOLVED_ADJUSTMENT" if document.adjustment_type else "NEEDS_CONTEXT",
        data_json=json.dumps({"schema_version": 1, "source_receipt_id": receipt.id,
            "vendor": receipt.vendor, "vendor_business_number": receipt.business_number,
            "date": str(receipt.date) if receipt.date else None,
            "taxable_supply_amount": receipt.taxable_supply_amount, "tax_exempt_amount": receipt.tax_exempt_amount,
            "vat_amount": receipt.vat_amount, "total_amount": receipt.transaction_amount if receipt.transaction_amount is not None else receipt.amount,
            "payment_amount": receipt.payment_amount, "subtotal_amount": receipt.subtotal_amount,
            "document": document.model_dump(mode="json"), "evidence_validation": facts.evidence_validation,
            "ocr_confirmed": True, "tax_analysis_confirmed": False}, ensure_ascii=False))
    session.add(transaction)
    session.flush()
    receipt.transaction_id = transaction.id
    session.add(receipt)
    return transaction


def transaction_out(session: Session, user_id: uuid.UUID, transaction: Transaction) -> dict:
    receipts = transaction_receipts(session, user_id, transaction.id)
    facts = json.loads(transaction.data_json)
    evidence = [ReceiptOut.model_validate(receipt).model_dump(mode="json") for receipt in receipts]
    conflicts = []
    for field in ("business_number", "taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount"):
        values = {receipt[field] for receipt in evidence if receipt[field] is not None}
        if len(values) > 1:
            conflicts.append(field)
    primary = next((receipt for receipt in evidence if receipt["id"] == facts.get("source_receipt_id")), None)
    statuses = {receipt["evidence_validation"]["validation_status"] for receipt in evidence}
    validation_status = "INVALID" if "INVALID" in statuses else "CONFLICT" if conflicts or "CONFLICT" in statuses else "INCOMPLETE" if not evidence or "INCOMPLETE" in statuses else "VALID"
    return {"id": transaction.id, "revision": transaction.revision, "workflow_status": transaction.workflow_status,
            "original_transaction_id": transaction.original_transaction_id, "adjustment_type": transaction.adjustment_type,
            "facts": facts, "receipts": evidence, "evidence_validation": {"validation_status": validation_status, "conflicts": conflicts},
            "canonical_receipt_id": facts.get("source_receipt_id"), "canonical_line_items": primary["line_items"] if primary else [],
            "aggregation_policy": "Use canonical facts and items once; evidence rows are not additional purchases.",
            "tax_analysis_confirmed": False, "integration_status": "LOCAL_CONTRACT_ONLY"}


@router.get("/transactions")
def list_transactions(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    transactions = session.exec(select(Transaction).where(Transaction.user_id == user.id)).all()
    return [transaction_out(session, user.id, transaction) for transaction in transactions]


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return transaction_out(session, user.id, owned_transaction(session, user.id, transaction_id))


@router.get("/transactions/{transaction_id}/evidence")
def get_evidence(transaction_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[ReceiptOut]:
    owned_transaction(session, user.id, transaction_id)
    return [ReceiptOut.model_validate(receipt) for receipt in transaction_receipts(session, user.id, transaction_id)]


@router.post("/transactions/{transaction_id}/evidence/validate")
def validate_evidence(transaction_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    owned_transaction(session, user.id, transaction_id)
    return {"receipts": [{"receipt_id": receipt.id, **ReceiptOut.model_validate(receipt).evidence_validation}
                         for receipt in transaction_receipts(session, user.id, transaction_id)], "deduction_status": "UNDETERMINED"}


@router.get("/transactions/{transaction_id}/line-items")
def get_items(transaction_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    owned_transaction(session, user.id, transaction_id)
    return [{"receipt_id": receipt.id, "position": row.position, **json.loads(row.data_json), "id": row.id}
            for receipt in transaction_receipts(session, user.id, transaction_id) for row in receipt.line_items]


class ItemUsageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1, strict=True)
    usage: Literal["UNKNOWN", "BUSINESS", "PERSONAL", "MIXED"]
    user_note: str | None = None


def lock_revision(session: Session, transaction: Transaction, expected: int) -> None:
    result = session.execute(sa_update(Transaction).where(Transaction.id == transaction.id, Transaction.revision == expected).values(revision=expected + 1))
    if result.rowcount != 1:
        session.rollback()
        raise AppException(409, "DATA_CONFLICT", "거래가 바뀌었습니다. 최신 상태를 확인하세요.")
    session.refresh(transaction)


@router.patch("/transactions/{transaction_id}/line-items/{item_id}")
def update_usage(transaction_id: str, item_id: str, payload: ItemUsageIn,
                 user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    transaction = owned_transaction(session, user.id, transaction_id)
    item = session.exec(select(LineItem).join(Receipt, Receipt.id == LineItem.receipt_id).where(
        LineItem.id == item_id, Receipt.transaction_id == transaction_id, Receipt.user_id == user.id)).first()
    if item is None:
        raise AppException(404, "NOT_FOUND", "품목을 찾을 수 없습니다.")
    lock_revision(session, transaction, payload.base_revision)
    data = json.loads(item.data_json)
    data.update(usage=payload.usage, user_note=payload.user_note)
    data.setdefault("sources", {})["usage"] = {"kind": "manual", "state": "READ"}
    item.data_json = StructuredItem.model_validate(data).model_dump_json()
    session.add(item)
    session.execute(sa_update(Receipt).where(Receipt.id == item.receipt_id, Receipt.user_id == user.id).values(revision=Receipt.revision + 1))
    session.commit()
    return transaction_out(session, user.id, transaction)


class AdjustmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1, strict=True)
    adjustment_type: Literal["RETURN", "CANCELLATION", "CORRECTION"]
    supply_date: date
    supply_amount: FiniteFloat | None = None
    taxable_supply_amount: FiniteFloat | None = None
    tax_exempt_amount: FiniteFloat | None = None
    vat_amount: FiniteFloat | None = None
    total_amount: FiniteFloat
    reason: str | None = None

    @model_validator(mode="after")
    def amounts_agree(self):
        from decimal import Decimal
        if self.adjustment_type in ("RETURN", "CANCELLATION") and (self.total_amount >= 0 or any(
            value is not None and value > 0 for value in (self.supply_amount, self.taxable_supply_amount, self.tax_exempt_amount, self.vat_amount))):
            raise ValueError("Return/cancellation amounts must preserve negative signs")
        parts = (self.taxable_supply_amount, self.tax_exempt_amount, self.vat_amount)
        if all(value is not None for value in parts) and sum(Decimal(str(v)) for v in parts) != Decimal(str(self.total_amount)):
            raise ValueError("Amount breakdown differs from total")
        if self.supply_amount is not None and self.vat_amount is not None and Decimal(str(self.supply_amount)) + Decimal(str(self.vat_amount)) != Decimal(str(self.total_amount)):
            raise ValueError("Net amount and VAT differ from total")
        return self


@router.post("/transactions/{transaction_id}/adjustments", status_code=201)
def create_adjustment(transaction_id: str, payload: AdjustmentIn, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    original = owned_transaction(session, user.id, transaction_id)
    if original.original_transaction_id or original.adjustment_type or original.workflow_status == "MERGED":
        raise AppException(409, "INVALID_ADJUSTMENT", "원거래에 조정거래를 연결하세요.")
    lock_revision(session, original, payload.base_revision)
    amount = json.loads(original.data_json).get("total_amount")
    prior = session.exec(select(Transaction).where(Transaction.original_transaction_id == transaction_id, Transaction.user_id == user.id,
        Transaction.workflow_status != "MERGED")).all()
    from decimal import Decimal
    returned = sum((Decimal(str(json.loads(t.data_json)["total_amount"])) for t in prior), Decimal(0))
    if amount is not None and Decimal(str(amount)) + returned + Decimal(str(payload.total_amount)) < 0:
        session.rollback()
        raise AppException(409, "INVALID_ADJUSTMENT", "조정 금액이 원거래의 남은 금액을 초과합니다.")
    adjustment = Transaction(user_id=user.id, original_transaction_id=original.id, adjustment_type=payload.adjustment_type,
        workflow_status="NEEDS_EVIDENCE", data_json=json.dumps({**payload.model_dump(mode="json", exclude={"base_revision"}),
            "ocr_confirmed": False, "tax_analysis_confirmed": False}, ensure_ascii=False))
    session.add(adjustment)
    session.commit()
    return transaction_out(session, user.id, adjustment)


class OriginalLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: int = Field(ge=1, strict=True)
    original_transaction_id: str
    original_revision: int = Field(ge=1, strict=True)


@router.patch("/transactions/{transaction_id}")
def link_original(transaction_id: str, payload: OriginalLinkIn,
                  user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    """Resolve a reviewed adjustment without recreating its receipt or signed facts."""
    adjustment = owned_transaction(session, user.id, transaction_id)
    original = owned_transaction(session, user.id, payload.original_transaction_id)
    if (adjustment.id == original.id or not adjustment.adjustment_type or adjustment.original_transaction_id
            or adjustment.workflow_status != "UNRESOLVED_ADJUSTMENT"
            or original.adjustment_type or original.workflow_status == "MERGED"):
        raise AppException(409, "INVALID_ADJUSTMENT", "미해결 조정거래와 일반 원거래를 선택하세요.")
    from decimal import Decimal
    facts, original_facts = json.loads(adjustment.data_json), json.loads(original.data_json)
    amount, original_amount = facts.get("total_amount"), original_facts.get("total_amount")
    if amount is None or original_amount is None or original_amount <= 0:
        raise AppException(409, "INVALID_ADJUSTMENT", "원거래와 조정거래의 금액을 먼저 확인하세요.")
    if adjustment.adjustment_type in ("RETURN", "CANCELLATION") and amount >= 0:
        raise AppException(409, "INVALID_ADJUSTMENT", "반품·취소 금액은 음수여야 합니다.")
    merchant, original_merchant = facts.get("vendor_business_number"), original_facts.get("vendor_business_number")
    if merchant and original_merchant and merchant != original_merchant:
        raise AppException(409, "INVALID_ADJUSTMENT", "거래처가 다른 원거래입니다.")
    try:
        # The original revision serializes all refund additions, including manual ones.
        lock_revision(session, original, payload.original_revision)
        lock_revision(session, adjustment, payload.base_revision)
        prior = session.exec(select(Transaction).where(Transaction.original_transaction_id == original.id,
            Transaction.user_id == user.id, Transaction.workflow_status != "MERGED")).all()
        adjusted = sum((Decimal(str(json.loads(t.data_json)["total_amount"])) for t in prior), Decimal(0))
        if Decimal(str(original_amount)) + adjusted + Decimal(str(amount)) < 0:
            raise AppException(409, "INVALID_ADJUSTMENT", "조정 금액이 원거래의 남은 금액을 초과합니다.")
        adjustment.original_transaction_id = original.id
        adjustment.workflow_status = "NEEDS_CONTEXT"
        session.add(adjustment)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return transaction_out(session, user.id, adjustment)


def duplicate_reason(left: Receipt, right: Receipt) -> str | None:
    if left.file_hash and left.file_hash == right.file_hash:
        return "SAME_FILE"
    if left.perceptual_hash and right.perceptual_hash and (int(left.perceptual_hash, 16) ^ int(right.perceptual_hash, 16)).bit_count() <= 6:
        return "SIMILAR_IMAGE"
    a = DocumentFacts.model_validate_json(left.document_json or "{}")
    b = DocumentFacts.model_validate_json(right.document_json or "{}")
    if all((a.approval_number, a.transaction_datetime, left.business_number, left.transaction_amount is not None)) and (
        a.approval_number, a.transaction_datetime, left.business_number, left.transaction_amount) == (
        b.approval_number, b.transaction_datetime, right.business_number, right.transaction_amount):
        return "SAME_APPROVAL_SIGNATURE"
    return None


def find_duplicates(session: Session, receipt: Receipt) -> None:
    session.flush()
    others = session.exec(select(Receipt).where(Receipt.user_id == receipt.user_id, Receipt.id != receipt.id)).all()
    for other in others:
        reason = duplicate_reason(receipt, other)
        low, high = sorted((receipt.id, other.id))
        existing = session.exec(select(ReconciliationIssue).where(ReconciliationIssue.user_id == receipt.user_id,
            ReconciliationIssue.receipt_id == low, ReconciliationIssue.candidate_receipt_id == high)).first()
        if existing is not None:
            existing.active = bool(reason)
            if reason and not existing.resolved:
                existing.reason = reason
            session.add(existing)
        elif reason:
            # Receipt edits can discover the same pair concurrently. Preserve an existing decision on conflict.
            dialect = session.get_bind().dialect.name
            if dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            elif dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                raise RuntimeError("Duplicate reconciliation requires SQLite or PostgreSQL")
            table = ReconciliationIssue.__table__
            statement = insert(table).values(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vat-ai/duplicates/{low}/{high}")),
                user_id=receipt.user_id, receipt_id=low, candidate_receipt_id=high, reason=reason, resolved=False, active=True)
            session.execute(statement.on_conflict_do_update(index_elements=["receipt_id", "candidate_receipt_id"],
                set_={"active": True, "reason": case((table.c.resolved.is_(False), reason), else_=table.c.reason)}))


@router.get("/reconciliation/issues")
def get_issues(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    issues = session.exec(select(ReconciliationIssue).where(ReconciliationIssue.user_id == user.id)).all()
    result = []
    for issue in issues:
        receipts = [session.get(Receipt, receipt_id) for receipt_id in (issue.receipt_id, issue.candidate_receipt_id)]
        result.append({"id": issue.id, "type": "DUPLICATE_SUSPECTED", "reason": issue.reason,
            "resolved": issue.resolved, "active": issue.active, "action": issue.action,
            "receipts": [{"id": r.id, "revision": r.revision, "transaction_id": r.transaction_id} for r in receipts if r and r.user_id == user.id]})
    return result


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["MERGE", "SEPARATE"]
    canonical_transaction_id: str | None = None
    transaction_revisions: dict[str, Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=dict)
    receipt_revisions: dict[int, Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=dict)


def merge_transactions(session: Session, user_id: uuid.UUID, canonical_id: str, source_id: str, payload: ResolveIn) -> None:
    canonical, source = (owned_transaction(session, user_id, id_) for id_ in (canonical_id, source_id))
    if canonical_id == source_id or any(t.workflow_status == "MERGED" or t.adjustment_type for t in (canonical, source)):
        raise AppException(409, "DATA_CONFLICT", "병합할 두 일반 거래를 다시 확인하세요.")
    a, b = json.loads(canonical.data_json), json.loads(source.data_json)
    for field in ("total_amount", "vendor_business_number"):
        if a.get(field) is not None and b.get(field) is not None and a[field] != b[field]:
            raise AppException(409, "DATA_CONFLICT", "금액이나 거래처가 다른 거래는 병합할 수 없습니다.")
    for transaction in (canonical, source):
        lock_revision(session, transaction, payload.transaction_revisions.get(transaction.id, -1))
    adjustments = session.exec(select(Transaction).where(Transaction.user_id == user_id,
        Transaction.original_transaction_id.in_((canonical_id, source_id)), Transaction.workflow_status != "MERGED")).all()
    if adjustments:
        from decimal import Decimal
        total = a.get("total_amount")
        adjusted = sum((Decimal(str(json.loads(item.data_json)["total_amount"])) for item in adjustments), Decimal(0))
        if total is None or Decimal(str(total)) + adjusted < 0:
            raise AppException(409, "INVALID_ADJUSTMENT", "병합 후 반품·취소 금액이 원거래 금액을 초과합니다. 조정거래를 먼저 확인하세요.")
        for adjustment in adjustments:
            lock_revision(session, adjustment, payload.transaction_revisions.get(adjustment.id, -1))
            if adjustment.original_transaction_id == source_id:
                adjustment.original_transaction_id = canonical_id
                session.add(adjustment)
    receipts = transaction_receipts(session, user_id, source_id)
    for receipt in receipts:
        update = session.execute(sa_update(Receipt).where(Receipt.id == receipt.id, Receipt.user_id == user_id,
            Receipt.transaction_id == source_id, Receipt.revision == payload.receipt_revisions.get(receipt.id, -1)).values(
                transaction_id=canonical_id, revision=Receipt.revision + 1))
        if update.rowcount != 1:
            session.rollback()
            raise AppException(409, "DATA_CONFLICT", "증빙 연결이 바뀌었습니다. 다시 확인하세요.")
    source.workflow_status = "MERGED"
    source.data_json = json.dumps({**b, "merged_into": canonical_id}, ensure_ascii=False)
    session.add(source)


@router.post("/reconciliation/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, payload: ResolveIn, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    issue = session.exec(select(ReconciliationIssue).where(ReconciliationIssue.id == issue_id, ReconciliationIssue.user_id == user.id)).first()
    if issue is None:
        raise AppException(404, "NOT_FOUND", "중복 후보를 찾을 수 없습니다.")
    result = session.execute(sa_update(ReconciliationIssue).where(ReconciliationIssue.id == issue_id,
        ReconciliationIssue.resolved.is_(False), ReconciliationIssue.active.is_(True)).values(resolved=True, action=payload.action))
    if result.rowcount != 1:
        session.rollback()
        raise AppException(409, "DATA_CONFLICT", "이미 해결되었거나 현재 일치하지 않는 후보입니다.")
    try:
        if payload.action == "MERGE":
            receipts = [session.get(Receipt, id_) for id_ in (issue.receipt_id, issue.candidate_receipt_id)]
            transaction_ids = {r.transaction_id for r in receipts if r and r.user_id == user.id}
            if None in transaction_ids or payload.canonical_transaction_id not in transaction_ids or len(transaction_ids) != 2:
                raise AppException(409, "DATA_CONFLICT", "확정된 두 거래와 대표 거래를 선택하세요.")
            source_id = next(id_ for id_ in transaction_ids if id_ != payload.canonical_transaction_id)
            merge_transactions(session, user.id, payload.canonical_transaction_id, source_id, payload)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"resolved": True, "action": payload.action}


class EvidenceLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: int = Field(gt=0, strict=True)
    base_revision: int = Field(ge=1, strict=True)
    receipt_revision: int = Field(ge=1, strict=True)
    source_transaction_revision: int | None = Field(default=None, ge=1, strict=True)
    original_revision: int | None = Field(default=None, ge=1, strict=True)
    related_transaction_revisions: dict[str, Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=dict)
    source_receipt_revisions: dict[int, Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=dict)


def link_adjustment_evidence(session: Session, user_id: uuid.UUID, canonical: Transaction, receipt: Receipt, payload: EvidenceLinkIn) -> None:
    from decimal import Decimal
    if not canonical.original_transaction_id or canonical.workflow_status not in ("NEEDS_EVIDENCE", "NEEDS_CONTEXT"):
        raise AppException(409, "INVALID_ADJUSTMENT", "원거래에 연결된 조정거래에 증빙을 추가하세요.")
    original = owned_transaction(session, user_id, canonical.original_transaction_id)
    source = owned_transaction(session, user_id, receipt.transaction_id) if receipt.transaction_id else None
    if original.workflow_status == "MERGED" or original.adjustment_type:
        raise AppException(409, "INVALID_ADJUSTMENT", "현재 원거래를 다시 확인하세요.")
    if source is None or source.workflow_status == "MERGED" or source.adjustment_type != canonical.adjustment_type:
        raise AppException(409, "INVALID_ADJUSTMENT", "같은 종류의 확정된 반품·취소 증빙을 선택하세요.")
    if source.original_transaction_id not in (None, original.id):
        raise AppException(409, "INVALID_ADJUSTMENT", "다른 원거래에 연결된 증빙입니다.")
    a, b, original_facts = (json.loads(t.data_json) for t in (canonical, source, original))
    if a.get("total_amount") is None or b.get("total_amount") is None:
        raise AppException(409, "DATA_CONFLICT", "조정 금액을 먼저 확인하세요.")
    for key in ("total_amount", "taxable_supply_amount", "tax_exempt_amount", "vat_amount"):
        if a.get(key) is not None and b.get(key) is not None and Decimal(str(a[key])) != Decimal(str(b[key])):
            raise AppException(409, "DATA_CONFLICT", "조정거래와 증빙의 금액이 다릅니다.")
    if a.get("supply_amount") is not None and b.get("taxable_supply_amount") is not None and b.get("tax_exempt_amount") is not None:
        if Decimal(str(a["supply_amount"])) != Decimal(str(b["taxable_supply_amount"])) + Decimal(str(b["tax_exempt_amount"])):
            raise AppException(409, "DATA_CONFLICT", "조정거래와 증빙의 부가세 제외 금액이 다릅니다.")
    merchant = b.get("vendor_business_number")
    if merchant and original_facts.get("vendor_business_number") and merchant != original_facts["vendor_business_number"]:
        raise AppException(409, "DATA_CONFLICT", "원거래와 거래처가 다른 증빙입니다.")
    evidence_date = b.get("document", {}).get("supply_date") or b.get("date")
    if a.get("supply_date") and evidence_date and a["supply_date"] != evidence_date:
        raise AppException(409, "DATA_CONFLICT", "조정거래와 증빙의 거래일을 확인하세요.")
    # Serialize against new refunds while removing a duplicate adjustment from aggregation.
    lock_revision(session, original, payload.original_revision or -1)
    lock_revision(session, canonical, payload.base_revision)
    lock_revision(session, source, payload.source_transaction_revision or -1)
    source_receipts = transaction_receipts(session, user_id, source.id)
    for linked in source_receipts:
        expected = payload.receipt_revision if linked.id == receipt.id else payload.source_receipt_revisions.get(linked.id, -1)
        result = session.execute(sa_update(Receipt).where(Receipt.id == linked.id, Receipt.user_id == user_id,
            Receipt.transaction_id == source.id, Receipt.confirmed.is_(True), Receipt.revision == expected).values(
                transaction_id=canonical.id, revision=Receipt.revision + 1))
        if result.rowcount != 1:
            raise AppException(409, "DATA_CONFLICT", "조정 증빙 연결이 바뀌었습니다. 다시 확인하세요.")
    combined = {**b, **{key: value for key, value in a.items() if value is not None}}
    combined.update(source_receipt_id=a.get("source_receipt_id") or receipt.id,
        document=a.get("document") or b.get("document"), ocr_confirmed=True, tax_analysis_confirmed=False)
    canonical.data_json = json.dumps(combined, ensure_ascii=False)
    canonical.workflow_status = "NEEDS_CONTEXT"
    source.workflow_status = "MERGED"
    source.data_json = json.dumps({**b, "merged_into": canonical.id}, ensure_ascii=False)
    session.add(canonical)
    session.add(source)


@router.post("/transactions/{transaction_id}/evidence")
def link_evidence(transaction_id: str, payload: EvidenceLinkIn, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    canonical = owned_transaction(session, user.id, transaction_id)
    receipt = session.exec(select(Receipt).where(Receipt.id == payload.receipt_id, Receipt.user_id == user.id)).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "증빙을 찾을 수 없습니다.")
    if not receipt.confirmed or receipt.revision != payload.receipt_revision:
        raise AppException(409, "DATA_CONFLICT", "최신 증빙을 확인하고 OCR을 먼저 확정하세요.")
    if receipt.transaction_id == transaction_id:
        if canonical.revision != payload.base_revision:
            raise AppException(409, "DATA_CONFLICT", "거래가 바뀌었습니다. 다시 확인하세요.")
        return transaction_out(session, user.id, canonical)
    try:
        if canonical.adjustment_type:
            link_adjustment_evidence(session, user.id, canonical, receipt, payload)
        elif receipt.transaction_id is not None:
            if payload.source_transaction_revision is None:
                raise AppException(409, "DATA_CONFLICT", "연결할 증빙의 현재 거래 버전도 확인하세요.")
            merge_transactions(session, user.id, transaction_id, receipt.transaction_id, ResolveIn(action="MERGE",
                canonical_transaction_id=transaction_id, transaction_revisions={**payload.related_transaction_revisions, transaction_id: payload.base_revision,
                    receipt.transaction_id: payload.source_transaction_revision},
                receipt_revisions={**payload.source_receipt_revisions, receipt.id: payload.receipt_revision}))
        else:
            if canonical.workflow_status == "MERGED" or canonical.adjustment_type:
                raise AppException(409, "DATA_CONFLICT", "일반 거래에 증빙을 연결하세요.")
            facts = json.loads(canonical.data_json)
            for field, value in (("total_amount", receipt.transaction_amount if receipt.transaction_amount is not None else receipt.amount),
                                 ("vendor_business_number", receipt.business_number)):
                if facts.get(field) is not None and value is not None and facts[field] != value:
                    raise AppException(409, "DATA_CONFLICT", "금액이나 거래처가 다른 증빙입니다.")
            lock_revision(session, canonical, payload.base_revision)
            result = session.execute(sa_update(Receipt).where(Receipt.id == receipt.id, Receipt.user_id == user.id,
                Receipt.revision == payload.receipt_revision, Receipt.transaction_id.is_(None), Receipt.confirmed.is_(True)).values(
                    transaction_id=transaction_id, revision=Receipt.revision + 1))
            if result.rowcount != 1:
                raise AppException(409, "DATA_CONFLICT", "증빙 연결이 바뀌었습니다. 다시 확인하세요.")
        session.commit()
    except Exception:
        session.rollback()
        raise
    return transaction_out(session, user.id, canonical)
