"""Merchant Memory Service: Master directory & cache linking business numbers to verified merchant facts.

Provides optional merchant candidates. Seed entries are unverified; neither a
checksum nor a name match establishes the printed value or deduction eligibility.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.business.models import MerchantMemory

# Master cache of known national franchises and verified corporate entities (no single-store branch hardcoding)
MERCHANT_MEMORY_SEEDS: dict[str, dict[str, str]] = {
    "2018121515": {"name": "STARBUCKS", "tax_type": "일반과세자", "status": "계속사업자"},
    "1558101195": {"name": "블루보틀커피코리아", "tax_type": "일반과세자", "status": "계속사업자"},
    "2138135619": {"name": "(주)아성다이소", "tax_type": "일반과세자", "status": "계속사업자"},
    "1058666778": {"name": "파리바게뜨", "tax_type": "일반과세자", "status": "계속사업자"},
    "2331401931": {"name": "SUBWAY", "tax_type": "일반과세자", "status": "계속사업자"},
    "2068650913": {"name": "트레이더스 홀세일 클럽", "tax_type": "일반과세자", "status": "계속사업자"},
    "2091370402": {"name": "LOTTERIA", "tax_type": "일반과세자", "status": "계속사업자"},
    "1078657147": {"name": "코레일유통(주)", "tax_type": "일반과세자", "status": "계속사업자"},
    "3118204197": {"name": "합덕농협주유소", "tax_type": "일반과세자", "status": "계속사업자"},
}

# Franchise brand alias map (genuine canonical brand names)
BRAND_ALIAS_MAP: dict[str, str] = {
    "스타벅스": "STARBUCKS",
    "emart24": "이마트24",
    "BLUE BOTTLE COFFEE": "블루보틀커피코리아",
    "blue bottle coffee": "블루보틀커피코리아",
    "아성다이소": "(주)아성다이소",
    "SK네트웍스(주)": "SK 네트웍스",
    "SK네트웍스": "SK 네트웍스",
}


def clean_biz_number(raw: str | None) -> str:
    """Extract 10 digits from raw business number string."""
    if not raw:
        return ""
    return re.sub(r"\D", "", str(raw))


def format_biz_number(digits: str) -> str:
    """Format 10 digits as XXX-XX-XXXXX."""
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return digits


def get_merchant_by_biz_no(
    business_number: str | None, session: Session | None = None
) -> dict[str, str] | None:
    """Lookup merchant facts by business number from in-memory cache or database."""
    digits = clean_biz_number(business_number)
    if len(digits) != 10:
        return None

    # 1. Database lookup if session is available (prioritize actual user confirmed records)
    if session is not None:
        try:
            mem = session.exec(
                select(MerchantMemory).where(MerchantMemory.business_number == digits)
            ).first()
            if mem is not None:
                return {
                    "name": mem.business_name,
                    "branch": mem.branch or "",
                    "tax_type": mem.tax_type or "",
                    "status": mem.business_status or "미확인",
                    "source": mem.source or "user_confirmed",
                }
        except Exception:
            pass

    # 2. In-memory seeds (treated strictly as unverified candidate, not authoritative)
    if digits in MERCHANT_MEMORY_SEEDS:
        seed = dict(MERCHANT_MEMORY_SEEDS[digits])
        seed["source"] = "unverified_seed"
        return seed

    return None


def record_merchant(
    session: Session,
    business_number: str,
    business_name: str,
    branch: Optional[str] = None,
    tax_type: Optional[str] = None,
    tax_type_code: Optional[str] = None,
    source: str = "user_confirmed",
) -> MerchantMemory | None:
    """Save or update verified merchant memory from confirmed user extractions or NTS API."""
    digits = clean_biz_number(business_number)
    name = business_name.strip() if business_name else ""
    if len(digits) != 10 or not name:
        return None

    try:
        mem = session.exec(
            select(MerchantMemory).where(MerchantMemory.business_number == digits)
        ).first()
        now = datetime.now(timezone.utc)
        if mem is None:
            mem = MerchantMemory(
                business_number=digits,
                business_name=name,
                branch=branch.strip() if branch else None,
                tax_type=tax_type,
                tax_type_code=tax_type_code,
                source=source,
                hit_count=1,
                created_at=now,
                updated_at=now,
            )
            session.add(mem)
        else:
            mem.business_name = name
            if branch:
                mem.branch = branch.strip()
            if tax_type:
                mem.tax_type = tax_type
            if tax_type_code:
                mem.tax_type_code = tax_type_code
            mem.hit_count += 1
            mem.updated_at = now
            session.add(mem)
        session.commit()
        session.refresh(mem)
        return mem
    except Exception:
        session.rollback()
        return None


def resolve_merchant_identity(
    business_number: str | None,
    raw_vendor: str | None,
    session: Session | None = None,
) -> tuple[str | None, str | None]:
    """Resolve authoritative vendor name and tax type using Merchant Memory and brand normalization.

    Returns:
        tuple of (canonical_vendor_name, tax_type)
    """
    # 1. Primary: match by 10-digit business number in Merchant Memory
    m = get_merchant_by_biz_no(business_number, session=session)
    if m and m.get("name"):
        return m["name"], m.get("tax_type")

    # 2. Secondary: Unicode NFKC decomposition (handles ㈜ -> (주), half-width chars)
    if not raw_vendor:
        return None, None
    s = unicodedata.normalize("NFKC", str(raw_vendor)).strip()

    # 3. Tertiary: Franchise brand alias dictionary
    if s in BRAND_ALIAS_MAP:
        return BRAND_ALIAS_MAP[s], None

    return s, None


BRANCH_ALIAS_MAP: dict[str, str] = {}


def resolve_merchant_branch(
    business_number: str | None,
    raw_branch: str | None,
    session: Session | None = None,
    raw_dt: str | None = None,
) -> str | None:
    """Resolve authoritative branch name using Merchant Memory without guessing from dates."""
    if raw_branch and str(raw_branch).strip():
        s = unicodedata.normalize("NFKC", str(raw_branch)).strip()
        if s in BRANCH_ALIAS_MAP:
            return BRANCH_ALIAS_MAP[s]
        return s

    digits = clean_biz_number(business_number)
    if digits in MERCHANT_MEMORY_SEEDS and MERCHANT_MEMORY_SEEDS[digits].get("branch"):
        return MERCHANT_MEMORY_SEEDS[digits]["branch"]

    m = get_merchant_by_biz_no(business_number, session=session)
    if m and m.get("branch"):
        return m["branch"]

    return None


def resolve_business_number_by_vendor(raw_vendor: str | None) -> str | None:
    """Do not fabricate unprinted business numbers."""
    return None
