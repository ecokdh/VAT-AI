import json
from datetime import date
from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine

from app.auth.models import User
from app.jobs.models import AsyncJob
from app.jobs import service as job_service
from app.jobs.worker import process_async_job
from app.receipts import service as receipt_service
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation
from app.receipts.storage import LocalFileStorage
from app.transactions.models import Transaction
from app.ocr_pipeline.contract import OcrPipelineResult, OcrStage, OcrStageStatus, OcrStageUpdate


def setup_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    user = User(email="jobs@example.com", password_hash="hash", name="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    return session, user


def test_ocr_job_persists_extracted_fields(monkeypatch, tmp_path):
    session, user = setup_session()
    storage = LocalFileStorage(tmp_path)
    stored = storage.save(user.id, b"image-bytes", "image/jpeg", "jpg")
    monkeypatch.setattr(receipt_service, "storage", storage)
    receipt = Receipt(user_id=user.id, image_url=stored.key, status="processing")
    session.add(receipt)
    session.flush()
    job = AsyncJob(user_id=user.id, job_type="ocr", payload_json=json.dumps({"receipt_id": receipt.id}))
    session.add(job)
    session.commit()

    class FakePipeline:
        def process(self, request, progress):
            assert request.image_bytes == b"image-bytes"
            assert request.content_type == "image/jpeg"
            progress(OcrStageUpdate(stage=OcrStage.TEXT_RECOGNITION, status=OcrStageStatus.COMPLETED, progress_percent=60))
            progress(OcrStageUpdate(stage=OcrStage.TRANSACTION_EXTRACTION, status=OcrStageStatus.COMPLETED, progress_percent=80))
            progress(OcrStageUpdate(stage=OcrStage.MISSING_FIELD_CHECK, status=OcrStageStatus.COMPLETED, progress_percent=100))
            return OcrPipelineResult(
                status="COMPLETED", vendor="문구점", amount=1100,
                transaction_date=date(2026, 3, 2), raw_text="문구점\n1,100원",
                pipeline_name="fake", pipeline_version="1",
            )

    monkeypatch.setattr("app.jobs.worker.load_pipeline", lambda _: FakePipeline())
    process_async_job(session, job)
    session.commit()
    session.refresh(receipt)

    assert receipt.status == "done"
    assert receipt.vendor == "문구점"
    assert receipt.amount == 1100
    assert receipt.processing_progress == 100
    assert receipt.stage_statuses["text_recognition"] == "completed"
    assert receipt.ocr_pipeline_name == "fake"
    assert json.loads(job.result_json)["receipt_status"] == "done"


def test_partial_ocr_is_done_for_user_correction(monkeypatch, tmp_path):
    session, user = setup_session()
    storage = LocalFileStorage(tmp_path)
    stored = storage.save(user.id, b"image-bytes", "image/jpeg", "jpg")
    monkeypatch.setattr(receipt_service, "storage", storage)
    receipt = Receipt(user_id=user.id, image_url=stored.key, status="processing")
    session.add(receipt)
    session.flush()
    job = AsyncJob(user_id=user.id, job_type="ocr", payload_json=json.dumps({"receipt_id": receipt.id}))
    session.add(job)
    session.commit()

    class PartialPipeline:
        def process(self, request, progress):
            return OcrPipelineResult(
                status="PARTIAL", vendor="문구점", raw_text="문구점", missing_fields=["amount", "transaction_date"],
                warnings=["금액과 거래일을 직접 확인해 주세요."], pipeline_name="fake", pipeline_version="1",
            )

    monkeypatch.setattr("app.jobs.worker.load_pipeline", lambda _: PartialPipeline())
    process_async_job(session, job)
    session.commit()
    session.refresh(receipt)
    assert receipt.status == "done"
    assert receipt.amount is None
    assert receipt.ocr_warnings == ["금액과 거래일을 직접 확인해 주세요."]
    assert receipt.stage_statuses["missing_field_check"] == "failed"


def test_receipt_inbox_lists_extraction_confirmed_receipts_without_transactions():
    session, user = setup_session()
    pending_review = Receipt(user_id=user.id, image_url="pending.jpg", status="done")
    ready_for_transaction = Receipt(user_id=user.id, image_url="ready.jpg", status="done", extraction_confirmed=True)
    already_confirmed_receipt = Receipt(user_id=user.id, image_url="confirmed.jpg", status="done", extraction_confirmed=True)
    session.add(pending_review)
    session.add(ready_for_transaction)
    session.add(already_confirmed_receipt)
    session.flush()
    session.add(Transaction(
        user_id=user.id,
        receipt_id=already_confirmed_receipt.id,
        direction="purchase",
        transaction_date=date(2026, 3, 2),
        vendor="문구점",
        total_amount=1100,
        state="confirmed",
    ))
    session.commit()

    inbox = job_service.list_receipt_inbox(session, user.id)
    assert [receipt.id for receipt in inbox] == [ready_for_transaction.id]


def test_confirm_extraction_persists_user_corrected_values():
    session, user = setup_session()
    receipt = Receipt(user_id=user.id, image_url="partial.jpg", status="done", vendor=None, amount=None, date=None,
                      ocr_missing_fields_json='["vendor", "amount", "transaction_date"]')
    session.add(receipt)
    session.commit()
    session.refresh(receipt)

    confirmed = job_service.confirm_receipt_extraction(
        session, user.id, receipt.id,
        ExtractionConfirmation(vendor="문구점", amount=1100, date=date(2026, 3, 2)),
    )
    assert confirmed.extraction_confirmed is True
    assert confirmed.vendor == "문구점"
    assert confirmed.amount == 1100
    assert confirmed.ocr_missing_fields == []


def test_user_retry_reuses_receipt_and_allows_one_retry():
    session, user = setup_session()
    receipt = Receipt(user_id=user.id, image_url="failed.jpg", status="failed", ocr_user_attempts=1)
    session.add(receipt)
    session.commit()
    session.refresh(receipt)

    job, updated = job_service.retry_receipt_ocr(session, user.id, receipt.id)
    assert job.job_type == "ocr"
    assert updated.status == "processing"
    assert updated.ocr_user_attempts == 2

    updated.status = "failed"
    session.add(updated)
    session.commit()
    try:
        job_service.retry_receipt_ocr(session, user.id, receipt.id)
        assert False, "second retry must be rejected"
    except Exception as error:
        assert getattr(error, "code", None) == "OCR_RETRY_LIMIT"


def test_pdf_job_generates_review_pdf_even_with_partial_estimate(monkeypatch, tmp_path):
    session, user = setup_session()
    storage = LocalFileStorage(tmp_path)
    monkeypatch.setattr(receipt_service, "storage", storage)
    fake_pdfkit = SimpleNamespace(
        configuration=lambda **kwargs: object(),
        from_string=lambda html, output, **kwargs: b"%PDF-review-copy",
    )
    monkeypatch.setitem(__import__("sys").modules, "pdfkit", fake_pdfkit)
    snapshot = {"period": "2026-H1", "status": "PARTIAL", "payable_estimate": 0, "notes": ["검토 1건"]}
    job = AsyncJob(user_id=user.id, job_type="pdf", payload_json=json.dumps(snapshot, ensure_ascii=False))

    process_async_job(session, job)

    file_key = json.loads(job.result_json)["file_key"]
    assert storage.read(file_key) == b"%PDF-review-copy"
