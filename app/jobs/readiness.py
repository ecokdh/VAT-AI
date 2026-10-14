"""Authoritative filing checks shared by the screen and PDF job creation."""
import re
from datetime import date
from sqlmodel import Session, select
from app.auth.models import User
from app.business.models import TaxProfileV2
from app.common.exceptions import AppException
from app.receipts.models import Receipt
from app.transactions.models import Transaction


def filter_bounds(period: str):
    match = re.fullmatch(r"(2025|2026)-(Q1|H1|Q3|H2|YEAR)", period)
    if not match:
        raise AppException(400, "UNSUPPORTED_TAX_PERIOD", "지원하지 않는 신고기간입니다.")
    year, part = int(match[1]), match[2]
    first, last = {"Q1": (1, 4), "H1": (1, 7), "Q3": (7, 10), "H2": (7, 13), "YEAR": (1, 13)}[part]
    return date(year, first, 1), date(year + 1, 1, 1) if last == 13 else date(year, last, 1)


def filing_readiness(session: Session, user: User, period: str, estimate: dict) -> dict:
    start, end = filter_bounds(period)
    profile = session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user.id)).first()
    rows = session.exec(select(Transaction).where(Transaction.user_id == user.id, Transaction.deleted_at.is_(None),
        Transaction.transaction_date >= start, Transaction.transaction_date < end)).all()
    receipts = session.exec(select(Receipt).outerjoin(Transaction, Transaction.receipt_id == Receipt.id).where(
        Receipt.user_id == user.id, Transaction.id.is_(None), Receipt.status == "done", Receipt.extraction_confirmed.is_(True),
        Receipt.date.is_(None) | ((Receipt.date >= start) & (Receipt.date < end)))).all()
    unconfirmed = len(receipts) + sum(row.state != "confirmed" for row in rows)
    pending = sum(row.state == "confirmed" and row.direction == "purchase" and row.review_status not in {"analyzed", "excluded"} for row in rows)
    total = len(rows) + len(receipts)
    checks = {
        "business": bool(profile and profile.confirmed_at),
        "transactions": total > 0 and unconfirmed == 0,
        "deductions": total > 0 and pending == 0,
        "estimate": estimate.get("status") == "COMPLETE" and estimate.get("payable_estimate") is not None,
    }
    return {"period": period, "checks": checks, "ready": all(checks.values()), "total": total,
        "unconfirmed": unconfirmed, "pending": pending,
        "deductible": sum(row.state == "confirmed" and row.direction == "purchase" and row.review_status == "analyzed" for row in rows),
        "nondeductible": sum(row.state == "confirmed" and row.direction == "purchase" and row.review_status == "excluded" for row in rows),
        "first_receipt_id": receipts[0].id if receipts else None}
