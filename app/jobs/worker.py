"""Small database-backed worker entry point.

Run with ``python -m app.jobs.worker`` in a separate process. The initial
handler deliberately holds purchases for review until a versioned, authoritative
legal source set is configured; it never lets an LLM invent a deductible amount.
"""
from __future__ import annotations

import json
import logging
from html import escape
import time
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.analysis.contract import AnalysisDecision, AnalysisRequest, BusinessFacts, TransactionFacts, load_analyzer
from app.core.database import engine
from app.core.config import settings
from app.jobs.models import AsyncJob
from app.receipts import service as receipt_service
from app.receipts.models import Receipt
from app.business.models import BusinessProfile, TaxProfileV2
from app.ocr_pipeline.contract import (
    OcrPipelineInput,
    OcrPipelineResult,
    OcrStageUpdate,
    load_pipeline,
)
from app.transactions.models import AnalysisRun, Transaction

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def process_analysis_run(session: Session, run: AnalysisRun) -> None:
    selected = json.loads(run.transaction_ids_json)
    results = []
    analyzer = load_analyzer(settings.DEDUCTION_ANALYZER)
    business_profile = session.exec(
        select(BusinessProfile).where(BusinessProfile.user_id == run.user_id)
    ).first()
    tax_profile = session.exec(
        select(TaxProfileV2).where(TaxProfileV2.user_id == run.user_id)
    ).first()
    suspension_periods = []
    if tax_profile and tax_profile.confirmed_at:
        try:
            suspension_periods = json.loads(tax_profile.suspension_periods_json or "[]")
        except (TypeError, json.JSONDecodeError):
            suspension_periods = []
    business_facts = BusinessFacts(
        verification_status=business_profile.verification_status if business_profile else None,
        business_status=business_profile.business_status if business_profile else None,
        tax_type=("general" if business_profile.tax_type_code == "01" else "simplified" if business_profile.tax_type_code == "02" else None) if business_profile else None,
        tax_profile_confirmed=bool(tax_profile and tax_profile.confirmed_at),
        entity_type=tax_profile.entity_type if tax_profile and tax_profile.confirmed_at else None,
        industry_category=tax_profile.industry_category if tax_profile and tax_profile.confirmed_at else None,
        industry_subtype=tax_profile.industry_subtype if tax_profile and tax_profile.confirmed_at else None,
        is_sme=tax_profile.is_sme if tax_profile and tax_profile.confirmed_at else None,
        business_start_date=tax_profile.business_start_date if tax_profile and tax_profile.confirmed_at else None,
        business_end_date=tax_profile.business_end_date if tax_profile and tax_profile.confirmed_at else None,
        suspension_periods=suspension_periods,
    )
    for selection in selected:
        transaction = session.exec(
            select(Transaction).where(
                Transaction.id == selection["id"],
                Transaction.user_id == run.user_id,
                Transaction.deleted_at.is_(None),
            )
        ).first()
        if transaction is None or transaction.revision != selection["revision"]:
            results.append({"transaction_id": selection["id"], "status": "SKIPPED_STALE"})
            continue
        receipt = session.get(Receipt, transaction.receipt_id) if transaction.receipt_id else None
        request = AnalysisRequest(
            run_id=run.id,
            transaction=TransactionFacts(
                transaction_id=transaction.id,
                revision=transaction.revision,
                transaction_date=transaction.transaction_date,
                vendor=transaction.vendor,
                description=transaction.description,
                purpose=transaction.purpose,
                ocr_text=receipt.ocr_raw if receipt else None,
                direction=transaction.direction,
                evidence_type=transaction.evidence_type,
                business_related=transaction.business_related,
                total_amount=transaction.total_amount,
                supply_amount=transaction.supply_amount,
                vat_amount=transaction.vat_amount,
                tax_treatment=transaction.tax_treatment,
                deemed_input_supply=transaction.deemed_input_supply,
                deemed_input_eligible=transaction.deemed_input_eligible,
                deemed_input_document_type=transaction.deemed_input_document_type,
            ),
            business=business_facts,
        )
        decision = AnalysisDecision.model_validate(analyzer.analyze(request))
        # A final disposition without a cited source is never allowed to enter
        # the tax estimate. The deterministic tax engine remains the only place
        # that computes amounts.
        if decision.disposition in {"DEDUCTIBLE", "NOT_DEDUCTIBLE"} and not decision.legal_references:
            decision = decision.model_copy(update={
                "disposition": "NEEDS_REVIEW",
                "reason": "판단 근거 자료가 연결되지 않아 검토가 필요합니다. " + decision.reason,
            })
        status_map = {
            "DEDUCTIBLE": ("analyzed", "SAFE"),
            "NOT_DEDUCTIBLE": ("excluded", "NOT_DEDUCTIBLE"),
            "NEEDS_REVIEW": ("caution", "CAUTION"),
            "INSUFFICIENT_INFO": ("insufficient_info", "CAUTION"),
        }
        transaction.review_status, transaction.risk_level = status_map[decision.disposition]
        transaction.deductible_vat = 0
        transaction.analysis_reason = decision.reason
        references = [item.model_dump(mode="json") for item in decision.legal_references]
        transaction.legal_references_json = json.dumps(references, ensure_ascii=False)
        session.add(transaction)
        results.append({
            "transaction_id": transaction.id,
            "revision": transaction.revision,
            "status": decision.disposition,
            "reason": decision.reason,
            "missing_information": decision.missing_information,
            "legal_references": references,
            "analyzer": {
                "name": decision.analyzer_name,
                "version": decision.analyzer_version,
                "knowledge_version": decision.knowledge_version,
            },
        })
    run.result_json = json.dumps(results, ensure_ascii=False)
    run.status = "COMPLETED"
    run.error_code = None
    run.error_message = None
    run.finished_at = _now()
    session.add(run)


def _review_pdf_html(snapshot: dict) -> str:
    labels = {
        "output_vat": "예상 매출세액",
        "eligible_input_vat": "일반 매입 공제액",
        "deemed_input_vat": "의제매입세액공제",
        "payable_estimate": "예상 납부세액",
    }
    rows = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(str(snapshot.get(key) if snapshot.get(key) is not None else '확인 필요'))}원</td></tr>"
        for key, label in labels.items()
    )
    notes = "".join(f"<li>{escape(str(note))}</li>" for note in snapshot.get("notes", []))
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><style>
    body {{ font-family: sans-serif; margin: 36px; color: #20242a; }} h1 {{ font-size: 22px; }}
    .notice {{ border: 1px solid #d98b00; padding: 12px; margin: 20px 0; }}
    table {{ width: 100%; border-collapse: collapse; }} th,td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
    li {{ margin: 8px 0; }}
    </style><body><h1>VAT-AI 신고 전 검토 자료</h1>
    <p>{escape(str(snapshot.get('period', '')))} · {escape(str(snapshot.get('tax_type', '')))} · 상태 {escape(str(snapshot.get('status', '')))}</p>
    <div class="notice">이 자료는 사용자의 참고를 위한 예상치이며 세무 신고서가 아닙니다. VAT-AI는 홈택스에 자동 제출하지 않습니다.</div>
    <table>{rows}</table><h2>검토 안내</h2><ul>{notes or '<li>추가 안내가 없습니다.</li>'}</ul></body></html>"""


def process_async_job(session: Session, job: AsyncJob) -> None:
    payload = json.loads(job.payload_json)
    if job.job_type == "ocr":
        receipt = session.exec(
            select(Receipt).where(Receipt.id == payload["receipt_id"], Receipt.user_id == job.user_id)
        ).first()
        if receipt is None:
            raise RuntimeError("OCR 작업의 영수증이 존재하지 않습니다.")
        image = receipt_service.storage.read(receipt.image_url)
        media_type = "image/png" if receipt.image_url.lower().endswith(".png") else "image/jpeg"
        pipeline = load_pipeline(settings.OCR_PIPELINE)
        stage_statuses = receipt.stage_statuses

        def report_progress(update: OcrStageUpdate) -> None:
            stage_statuses[update.stage.value] = update.status.value
            receipt.processing_stage = update.stage.value
            receipt.processing_progress = update.progress_percent
            receipt.stage_statuses_json = json.dumps(stage_statuses, ensure_ascii=False)
            session.add(receipt)
            session.commit()

        result = OcrPipelineResult.model_validate(pipeline.process(
            OcrPipelineInput(
                receipt_id=receipt.id,
                content_type=media_type,
                image_bytes=image,
            ),
            report_progress,
        ))
        for stage_name in ("photo_quality", "text_recognition", "transaction_extraction"):
            if stage_statuses.get(stage_name) in {None, "pending", "processing"}:
                stage_statuses[stage_name] = "completed"
        if stage_statuses.get("missing_field_check") in {None, "pending", "processing"}:
            stage_statuses["missing_field_check"] = "failed" if result.status in {"PARTIAL", "FAILED"} else "completed"
        receipt.stage_statuses_json = json.dumps(stage_statuses, ensure_ascii=False)
        receipt.vendor = result.vendor
        receipt.amount = result.amount
        receipt.date = result.transaction_date
        receipt.ocr_raw = result.raw_text
        receipt.ocr_warnings_json = json.dumps(result.warnings, ensure_ascii=False)
        receipt.ocr_missing_fields_json = json.dumps(result.missing_fields, ensure_ascii=False)
        receipt.ocr_pipeline_name = result.pipeline_name
        receipt.ocr_pipeline_version = result.pipeline_version
        receipt.retention_status = result.retention_status
        receipt.status = "failed" if result.status == "FAILED" else "done"
        receipt.processing_stage = "complete" if result.status != "FAILED" else "failed"
        receipt.processing_progress = 100 if result.status != "FAILED" else receipt.processing_progress
        job.result_json = json.dumps({
            "receipt_id": receipt.id,
            "receipt_status": receipt.status,
            "pipeline_status": result.status,
            "missing_fields": result.missing_fields,
            "warnings": result.warnings,
            "pipeline_name": result.pipeline_name,
            "pipeline_version": result.pipeline_version,
        }, ensure_ascii=False)
        session.add(receipt)
        return
    if job.job_type == "pdf":
        import pdfkit

        config = pdfkit.configuration(wkhtmltopdf=settings.PDFKIT_WKHTMLTOPDF_PATH or None)
        pdf_bytes = pdfkit.from_string(
            _review_pdf_html(payload),
            False,
            options={"encoding": "UTF-8", "quiet": ""},
            configuration=config,
        )
        stored = receipt_service.storage.save(job.user_id, pdf_bytes, "application/pdf", "pdf")
        job.result_json = json.dumps({"file_key": stored.key}, ensure_ascii=False)
        return
    raise RuntimeError(f"지원하지 않는 작업 유형: {job.job_type}")


def process_one() -> bool:
    """Claim and process one persisted OCR, PDF, or analysis job."""
    with Session(engine) as session:
        async_job = session.exec(
            select(AsyncJob)
            .where(AsyncJob.status == "PENDING")
            .order_by(AsyncJob.created_at)
            .with_for_update(skip_locked=True)
        ).first()
        if async_job is not None:
            async_job.status = "PROCESSING"
            async_job.attempts += 1
            async_job.started_at = _now()
            session.add(async_job)
            session.commit()
            session.refresh(async_job)
            try:
                process_async_job(session, async_job)
                async_job.status = "COMPLETED"
                async_job.error_code = None
                async_job.error_message = None
                async_job.finished_at = _now()
                session.add(async_job)
                session.commit()
            except Exception as exc:
                session.rollback()
                async_job = session.get(AsyncJob, async_job.id)
                if async_job is None:
                    logger.exception("Async job disappeared during processing")
                    return True
                async_job.error_code = "ASYNC_JOB_FAILED"
                async_job.error_message = str(exc)[:1000]
                async_job.finished_at = _now()
                async_job.status = "PENDING" if async_job.attempts < async_job.max_attempts else "FAILED"
                if async_job.status == "PENDING":
                    async_job.finished_at = None
                elif async_job.job_type == "ocr":
                    try:
                        receipt_id = json.loads(async_job.payload_json)["receipt_id"]
                        receipt = session.get(Receipt, receipt_id)
                        if receipt is not None and receipt.user_id == async_job.user_id:
                            receipt.status = "failed"
                            receipt.processing_stage = "failed"
                            receipt.stage_statuses_json = json.dumps({
                                **receipt.stage_statuses, "text_recognition": "failed"
                            }, ensure_ascii=False)
                            receipt.ocr_warnings_json = json.dumps(["증빙 분석 작업에 실패했습니다. 같은 사진으로 한 번 더 시도할 수 있습니다."], ensure_ascii=False)
                            session.add(receipt)
                    except (KeyError, ValueError, TypeError):
                        logger.exception("Failed to mark receipt after OCR job failure")
                session.add(async_job)
                session.commit()
                logger.exception("Async job %s failed", async_job.id)
            return True
        # FOR UPDATE SKIP LOCKED permits multiple PostgreSQL workers. SQLite
        # test runs are single-worker and simply ignore the locking clause.
        run = session.exec(
            select(AnalysisRun)
            .where(AnalysisRun.status == "PENDING")
            .order_by(AnalysisRun.created_at)
            .with_for_update(skip_locked=True)
        ).first()
        if run is None:
            return False
        run.status = "PROCESSING"
        run.attempts += 1
        run.started_at = _now()
        session.add(run)
        session.commit()
        session.refresh(run)
        try:
            process_analysis_run(session, run)
            session.commit()
        except Exception as exc:  # persist retry state before worker continues
            session.rollback()
            run = session.get(AnalysisRun, run.id)
            if run is None:
                logger.exception("Analysis run disappeared during processing")
                return True
            run.error_code = "ANALYSIS_FAILED"
            run.error_message = str(exc)[:1000]
            run.finished_at = _now()
            if run.attempts < run.max_attempts:
                run.status = "PENDING"
                run.finished_at = None
            else:
                run.status = "FAILED"
            session.add(run)
            session.commit()
            logger.exception("Analysis run %s failed", run.id)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        if not process_one():
            time.sleep(1)


if __name__ == "__main__":
    main()
