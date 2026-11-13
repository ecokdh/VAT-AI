import json
from datetime import date, datetime, timezone

import httpx
import pytest
from pypdf import PdfReader
from sqlmodel import Session, SQLModel, create_engine

from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.common.exceptions import AppException
from app.jobs import service as job_service
from app.jobs.worker import process_async_job
from app.receipts import service as receipt_service
from app.receipts.storage import LocalFileStorage
from app.sales_filing import service as sales_filing
from app.sales_monthly.models import MonthlySalesDocument
from app.transactions import service
from app.transactions.schemas import TransactionCreate
from app.vat_return.fill import fill_page1
from app.vat_return.returns import build_vat_return
from app.vat_return.verifier import verify


def setup_session(tax_type_code="01"):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="return@example.com", password_hash="hash", name="김대표")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(BusinessProfile(user_id=user.id, business_number="6100110001", business_name="카페 느린오후",
                                tax_type="일반과세자", tax_type_code=tax_type_code, business_type="음식점업",
                                business_item="커피", industry_code="552202"))
    session.commit()
    return session, user


def add(session, user, direction, evidence, supply, review="analyzed", fixed=False, business_related=True):
    item = service.create_transaction(session, user.id, TransactionCreate(
        direction=direction, transaction_date=date(2026, 3, 2), vendor="거래처", description="품목",
        evidence_type=evidence, business_related=business_related, total_amount=supply * 11 // 10,
        supply_amount=supply, vat_amount=supply // 10, tax_treatment="standard",
    ))
    item = service.confirm_transaction(session, user.id, item.id)
    if direction == "purchase":
        item.review_status = review
        item.risk_level = {"analyzed": "SAFE", "excluded": "NOT_DEDUCTIBLE", "caution": "CAUTION"}[review]
        item.is_fixed_asset = fixed
        session.add(item)
        session.commit()
    return item


def finalize_sales(session, user, invoice=0, card=0, period="2026-H1"):
    """신고용 매출 집계를 홈택스 세금계산서·카드 자료로 확정한다. 금액이 0인 출처는 해당 없음으로 둔다."""
    session.add(TaxProfileV2(user_id=user.id, entity_type="individual", confirmed_at=datetime.now(timezone.utc)))
    session.commit()
    supplies = {"hometax_sales_invoice": ("매출세금계산서", invoice), "hometax_card": ("홈택스카드", card)}
    for source in sales_filing.SOURCES:
        doc_type, supply = supplies.get(source, (None, 0))
        if not supply:
            sales_filing.update_source(session, user, period, source, status="해당 없음 확인", query_start=None,
                                       query_end=None, basis=None, document_ids=[], reason="해당 매출 없음")
            continue
        row = {"범위": "건별", "작성일": "2026-03-02", "과세구분": "과세",
               "공급가액": supply, "부가세": supply // 10, "합계금액": supply * 11 // 10}
        evidence = {"문서유형": doc_type, "기간시작": "2026-01-01", "기간종료": "2026-06-30", "기준일종류": "작성일", "내역": [row]}
        doc = MonthlySalesDocument(
            user_id=user.id, image_key=source, image_mime="image/png", image_sha256=source, status="reviewed",
            raw_prediction_json="{}", ocr_json="{}", model_response_json="{}", contract_version="test",
            review_json=json.dumps({"사업장": {"사업자등록번호": "6100110001"}, "매출증빙": evidence}, ensure_ascii=False),
        )
        session.add(doc)
        session.commit()
        sales_filing.update_source(session, user, period, source, status="확인 완료", query_start=date(2026, 1, 1),
                                   query_end=date(2026, 6, 30), basis="작성일", document_ids=[doc.id], reason=None)
    return sales_filing.finalize(session, user, period)


def sample_return(session, user):
    finalize_sales(session, user, invoice=1_000_000, card=2_000_000)
    add(session, user, "purchase", "tax_invoice", 500_000)
    add(session, user, "purchase", "tax_invoice", 300_000, fixed=True)
    add(session, user, "purchase", "card_receipt", 100_000)
    add(session, user, "purchase", "tax_invoice", 200_000, review="excluded")
    add(session, user, "purchase", "card_receipt", 70_000, review="caution")
    service.save_filing_input(session, user.id, "2026-H1", 50_000)
    return build_vat_return(session, user, "2026-H1")


def test_rows_follow_form_split_and_match_estimate():
    session, user = setup_session()
    result = sample_return(session, user)
    v = result["values"]

    assert (v["r1.amount"], v["r1.tax"]) == ("1,000,000", "100,000")
    assert (v["r3.amount"], v["r3.tax"]) == ("2,000,000", "200,000")
    assert v["r9.tax"] == "300,000"
    # 받은 세금계산서는 불공제분까지 (10)에 적고 (17)에서 뺀다. 고정자산은 (12)로 간다.
    assert (v["r10.amount"], v["r10.tax"]) == ("700,000", "70,000")
    assert (v["r12.amount"], v["r12.tax"]) == ("300,000", "30,000")
    assert v["r15.tax"] == "10,000"
    assert v["r17.tax"] == "20,000"
    assert v["r18.tax"] == "90,000"
    assert v["rda.tax"] == "210,000"
    assert v["r24.tax"] == "50,000"
    # 개인사업자: (3) 발행분 공급대가 2,200,000원의 1.3%를 (20) 발행세액공제로 뺀다.
    assert (v["r20.amount"], v["r20.tax"], v["r21.tax"]) == ("2,200,000", "28,600", "28,600")
    assert v["r30.tax"] == "131,400"
    assert (v["report.final"], v["period.term"], v["period.to_month"], v["period.to_day"]) == ("V", "1", "6", "30")
    assert (v["biz.reg_no"], v["base31.code"], v["base31.amount"]) == ("610-01-10001", "552202", "3,000,000")

    estimate = service.calculate_period_estimate(session, user, "2026-H1", None)
    assert int(v["r18.tax"].replace(",", "")) == estimate["eligible_input_vat"]
    assert int(v["rda.tax"].replace(",", "")) - int(v["r21.tax"].replace(",", "")) == estimate["payable_estimate"]
    assert not any("예상세액 계산과 다릅니다" in note for note in result["notes"])
    assert any("확인하지 않은 매입 1건" in note for note in result["notes"])


def test_simplified_taxpayer_is_not_supported():
    session, user = setup_session(tax_type_code="02")
    with pytest.raises(AppException):
        build_vat_return(session, user, "2026-YEAR")


def test_filled_pdf_keeps_six_pages_and_prints_values():
    pdf = fill_page1({"biz.name": "카페 느린오후", "r30.tax": "160,000"})
    reader = PdfReader(__import__("io").BytesIO(pdf))
    assert len(reader.pages) == 6
    text = reader.pages[0].extract_text()
    assert "카페 느린오후" in text and "160,000" in text


class FakeReader:
    def __init__(self, values=None, error=None):
        self.values, self.error = values, error

    def read(self, image_png):
        assert image_png.startswith(b"\x89PNG")
        if self.error:
            raise self.error
        return self.values


def test_verification_reports_only_mismatched_fields():
    expected = {"r9.tax": "300,000", "r30.tax": "160,000"}
    png = b"\x89PNG..."
    assert verify(expected, png, None)["status"] == "skipped"
    assert verify(expected, png, FakeReader(dict(expected)))["status"] == "passed"
    result = verify(expected, png, FakeReader({"r9.tax": "300,000", "r30.tax": "180,000", "r1.tax": "1"}))
    assert result["status"] == "mismatch"
    assert [(m["field"], m["expected"], m["read"]) for m in result["mismatches"]] == [("r1.tax", "", "1"), ("r30.tax", "160,000", "180,000")]
    assert verify(expected, png, FakeReader(error=httpx.ConnectError("down")))["status"] == "error"


def test_worker_builds_pdf_and_attaches_verification(monkeypatch, tmp_path):
    session, user = setup_session()
    finalize_sales(session, user, card=2_000_000)
    storage = LocalFileStorage(tmp_path)
    monkeypatch.setattr(receipt_service, "storage", storage)
    monkeypatch.setattr("app.vat_return.verifier.load_reader", lambda: None)
    job = job_service.enqueue_vat_return(session, user, "2026-H1", reviewed=True)

    process_async_job(session, job)

    result = json.loads(job.result_json)
    assert result["verification"]["status"] == "skipped"
    assert result["payable"] == 171_400  # 200,000 − 신용카드 발행세액공제 28,600
    assert storage.read(result["file_key"]).startswith(b"%PDF")
