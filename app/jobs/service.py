import json
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.auth.models import User
from app.core.config import settings
from app.common.exceptions import AppException
from app.jobs.models import AsyncJob
from app.receipts import service as receipt_service
from app.receipts.models import Receipt
from app.receipts.schemas import ExtractionConfirmation
from app.transactions.models import Transaction
from app.transactions.service import calculate_period_estimate


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_receipt_ocr(session: Session, user_id: uuid.UUID, content: bytes, content_type: str | None, direction: str = "purchase"):
    media_type, extension = receipt_service.validate_image(content, content_type)
    try:
        stored = receipt_service.storage.save(user_id, content, media_type, extension)
    except OSError as exc:
        raise AppException(500, "STORAGE_ERROR", "파일 저장에 실패했습니다.") from exc
    initial_stages = {
        "photo_quality": "completed",
        "text_recognition": "processing",
        "transaction_extraction": "pending",
        "missing_field_check": "pending",
    }
    luna_local = settings.OCR_PIPELINE == 'app.ocr_pipeline.luna:create_pipeline'
    if luna_local:
        initial_stages['photo_quality'] = 'skipped'
    receipt = Receipt(
        user_id=user_id,
        image_url=stored.key,
        direction=direction,
        status="processing",
        processing_stage="text_recognition",
        processing_progress=20,
        stage_statuses_json=json.dumps(initial_stages),
    )
    commit_attempted = False
    try:
        session.add(receipt)
        session.flush()
        job = AsyncJob(
            user_id=user_id,
            job_type="ocr",
            max_attempts=1 if luna_local else 3,
            payload_json=json.dumps({"receipt_id": receipt.id}, ensure_ascii=False),
        )
        session.add(job)
        commit_attempted = True
        session.commit()
    except Exception as exc:
        session.rollback()
        if not commit_attempted:
            try:
                receipt_service.storage.delete(stored.key)
            except Exception:
                pass
        raise AppException(500, "DATABASE_ERROR", "OCR 작업을 저장하지 못했습니다.") from exc
    session.refresh(receipt)
    session.refresh(job)
    return job, receipt


def enqueue_pdf(session: Session, user: User, period: str, reviewed: bool = False) -> AsyncJob:
    estimate = calculate_period_estimate(session, user, period, None)
    from app.jobs.readiness import filing_readiness
    readiness = filing_readiness(session, user, period, estimate)
    if not reviewed or not readiness["ready"]:
        raise AppException(409, "FILING_NOT_READY", "사업자정보, 거래 확정, 공제 검토와 예상세액 검토를 모두 완료해 주세요.")
    job = AsyncJob(
        user_id=user.id,
        job_type="pdf",
        payload_json=json.dumps(estimate, ensure_ascii=False),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, user_id: uuid.UUID, job_id: uuid.UUID) -> AsyncJob:
    job = session.exec(select(AsyncJob).where(AsyncJob.id == job_id, AsyncJob.user_id == user_id)).first()
    if job is None:
        raise AppException(404, "NOT_FOUND", "작업을 찾을 수 없습니다.")
    return job


def list_receipt_inbox(session: Session, user_id: uuid.UUID) -> list[Receipt]:
    """Extraction-confirmed OCR results that are not yet transaction records."""
    statement = (
        select(Receipt)
        .outerjoin(Transaction, Transaction.receipt_id == Receipt.id)
        .where(
            Receipt.user_id == user_id,
            Receipt.status == "done",
            Receipt.extraction_confirmed.is_(True),
            Transaction.id.is_(None),
        )
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
    )
    return list(session.exec(statement).all())


def confirm_receipt_extraction(
    session: Session, user_id: uuid.UUID, receipt_id: int, data: ExtractionConfirmation
) -> Receipt:
    receipt = session.exec(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    if receipt.status not in ("done", "needs_edit"):
        raise AppException(409, "OCR_NOT_COMPLETE", "OCR 완료 후 추출 결과를 확인해 주세요.")
    if not data.vendor.strip():
        raise AppException(400,'VALIDATION_ERROR','거래처를 입력해 주세요.')
    existing = session.exec(select(Transaction).where(Transaction.receipt_id == receipt.id)).first()
    if existing is not None:
        raise AppException(409,'TRANSACTION_ALREADY_CREATED','이미 거래로 저장된 증빙입니다. 보관함에서 거래 정보를 확인해 주세요.')
    before_details=receipt.details
    if data.details is not None:
        receipt.details_json=data.details.model_dump_json()
    if data.document is not None:
        existing = session.exec(select(Transaction).where(Transaction.receipt_id == receipt_id)).first()
        if existing is not None:
            raise AppException(409, 'TRANSACTION_EXISTS', '이미 등록된 거래는 보관함의 거래 수정 화면에서 변경해 주세요.')
        try:
            original = json.loads(receipt.ocr_raw or '')
            if not isinstance(original, dict):
                original = {'engine':'legacy','original_text':receipt.ocr_raw}
        except (ValueError, TypeError):
            original = {'engine':'legacy','original_text':receipt.ocr_raw}
        original.setdefault('original_details',before_details)
        old_fields = (original.get('document') or {}).get('fields') or {}
        orig_items = (original.get('document') or {}).get('items') or []
        corrected = data.document.model_dump(mode='json')
        used_sources: set[int] = set()
        resolved_sources: dict[int, int | None] = {}

        def _orig_raw_name(orig_item: dict) -> str | None:
            return orig_item.get('raw_name') if 'raw_name' in orig_item else orig_item.get('name')

        # 1st pass: explicit source_row or explicit user-added row (source_row=None)
        for idx, item_model in enumerate(data.document.items):
            if 'source_row' in item_model.model_fields_set:
                src = item_model.source_row
                if src is None:
                    resolved_sources[idx] = None
                else:
                    if src < 0 or src >= len(orig_items) or src in used_sources:
                        raise AppException(400, 'VALIDATION_ERROR', '원본 품목 참조 번호가 올바르지 않습니다.')
                    used_sources.add(src)
                    resolved_sources[idx] = src

        # Legacy references require unique content matches; never guess by position.
        for idx, item_model in enumerate(data.document.items):
            if idx in resolved_sources: continue
            candidates=[k for k,o in enumerate(orig_items) if k not in used_sources
                and item_model.name in (o.get('name'),_orig_raw_name(o))
                and all(getattr(item_model,key)==o.get(key) for key in ('quantity','unit_price','line_amount','row_type'))]
            if len(candidates)!=1:
                raise AppException(400,'SOURCE_REFERENCE_REQUIRED','품목 원본 연결을 확인해 주세요. 신규 행은 원본 번호를 비워 추가해 주세요.')
            resolved_sources[idx]=candidates[0];used_sources.add(candidates[0])

        for idx, item_dict in enumerate(corrected['items']):
            src = resolved_sources.get(idx)
            if src is not None:
                item_dict['raw_name'] = _orig_raw_name(orig_items[src])
                item_dict['source_row'] = src
            else:
                item_dict['raw_name'] = None
                item_dict['source_row'] = None

        from app.receipts.details import project_luna_details
        receipt.details_json=json.dumps(project_luna_details(corrected,receipt.details),ensure_ascii=False)
        from app.receipts.questions import validated_answers, facts, VERSION
        from app.business.models import TaxProfileV2
        profile=session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id==user_id)).first()
        answers=validated_answers(corrected,data.question_answers,receipt.direction,profile)
        related,answer_purpose=facts(answers)
        original['review'] = {
            'question_answers':answers,'question_version':VERSION,
            'document':corrected,'purpose':data.purpose.strip() if data.purpose else answer_purpose,
            'evidence_type':data.evidence_type,'business_related':related if answers else data.business_related,'tax_treatment':data.tax_treatment,
            'field_sources':{k:'user_edit' if v != old_fields.get(k) else 'user_confirmed' for k,v in corrected['fields'].items()},
            'saved_at':_now().isoformat(),'user_id':str(user_id),
        }
        receipt.ocr_raw = json.dumps(original,ensure_ascii=False,separators=(',',':'))
    receipt.vendor = data.vendor.strip()
    receipt.amount = data.amount
    receipt.date = data.date
    receipt.status = "done"
    receipt.extraction_confirmed = True
    receipt.ocr_missing_fields_json = "[]"
    session.add(receipt)
    session.commit()
    session.refresh(receipt)

    try:
        biz_no = None
        if data.document and data.document.fields:
            biz_no = getattr(data.document.fields, 'business_number', None)
        if not biz_no and receipt.details:
            biz_no = receipt.details.get('business_number')
        if biz_no:
            from app.business.merchant_memory import record_merchant
            record_merchant(session, biz_no, receipt.vendor, source="user_confirmed")
    except Exception:
        pass

    return receipt


def retry_receipt_ocr(session: Session, user_id: uuid.UUID, receipt_id: int):
    luna_local = settings.OCR_PIPELINE == 'app.ocr_pipeline.luna:create_pipeline'
    receipt = session.exec(
        select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
    ).first()
    if receipt is None:
        raise AppException(404, "NOT_FOUND", "영수증을 찾을 수 없습니다.")
    if receipt.status != "failed":
        raise AppException(409, "OCR_RETRY_NOT_AVAILABLE", "실패한 OCR 작업만 다시 시도할 수 있습니다.")
    if receipt.ocr_user_attempts >= 2:
        raise AppException(409, "OCR_RETRY_LIMIT", "같은 사진으로 재시도할 수 있는 횟수를 모두 사용했습니다.")
    receipt.ocr_user_attempts += 1
    receipt.status = "processing"
    receipt.processing_stage = "text_recognition"
    receipt.processing_progress = 20
    receipt.stage_statuses_json = json.dumps({
        "photo_quality": "skipped" if luna_local else "completed", "text_recognition": "processing",
        "transaction_extraction": "pending", "missing_field_check": "pending",
    })
    receipt.ocr_warnings_json = "[]"
    receipt.ocr_missing_fields_json = "[]"
    job = AsyncJob(
        user_id=user_id,
        job_type="ocr",
        max_attempts=1 if luna_local else 3,
        payload_json=json.dumps({"receipt_id": receipt.id}, ensure_ascii=False),
    )
    session.add(receipt)
    session.add(job)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise AppException(500, "DATABASE_ERROR", "OCR 재시도 작업을 저장하지 못했습니다.") from exc
    session.refresh(job)
    return job, receipt
