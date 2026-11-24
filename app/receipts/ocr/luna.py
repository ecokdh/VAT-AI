"""MVP worker adapter for Luna photo / photo + General OCR recognition."""
import asyncio,hashlib,json
from app.receipts.ocr.contract import OcrPipelineResult,OcrStage,OcrStageStatus,OcrStageUpdate
from app.receipts.ocr import luna_client
from app.receipts.ocr.luna_low_contract import CONTRACT_VERSION

async def recognize(image_bytes: bytes, mime_type: str = "image/jpeg"):
    return await luna_client.recognize(image_bytes, mime_type)

class LunaLowPipeline:
    def __init__(self, input_mode=None, *, cached_ocr=None):
        self.input_mode = input_mode
        self.cached_ocr = cached_ocr

    def process(self,request,report_progress):
        def stage(s,state,n,message):report_progress(OcrStageUpdate(stage=s,status=state,progress_percent=n,message=message))
        from app.receipts.ocr.image_utils import prepare_receipt_image
        from app.receipts.ocr.routing_rules import apply_post_extraction_checks

        input_bytes, input_mime, orientation_meta = prepare_receipt_image(
            request.image_bytes, request.content_type, report_progress
        )
        stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.PROCESSING,25,'증빙 글자를 인식하고 있습니다.')
        def ocr_done():
            stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.COMPLETED,45,'글자 인식을 마쳤습니다.')
            stage(OcrStage.TRANSACTION_EXTRACTION,OcrStageStatus.PROCESSING,50,'거래 정보와 금액을 구분하고 있습니다.')
        token=luna_client.on_ocr_done.set(ocr_done)
        try:
            if self.cached_ocr is not None:
                response = asyncio.run(luna_client.recognize(input_bytes, input_mime, input_mode=self.input_mode, cached_ocr=self.cached_ocr))
            else:
                response = asyncio.run(recognize(input_bytes, input_mime) if self.input_mode is None else luna_client.recognize(input_bytes, input_mime, input_mode=self.input_mode))
        except luna_client.LunaFailure as exc:
            for s in [OcrStage.TEXT_RECOGNITION,OcrStage.TRANSACTION_EXTRACTION,OcrStage.MISSING_FIELD_CHECK]:stage(s,OcrStageStatus.FAILED,30,'문서 인식 실패: '+exc.code)
            return OcrPipelineResult(status='FAILED',raw_text=json.dumps({'engine':'luna_low','error_code':exc.code,'ocr':getattr(exc,'ocr',None),'confirmed':False}),warnings=['문서 인식 실패: '+exc.code],missing_fields=['vendor','amount','transaction_date'],pipeline_name='luna_low',pipeline_version=CONTRACT_VERSION,doc_type=None,support_status=None,issues=[],affected_regions=[],issue_code=exc.code,guide_message='통신 또는 일시적인 처리 오류로 분석을 완료하지 못했습니다.')
        finally:luna_client.on_ocr_done.reset(token)
        if response['image_sha256']!=hashlib.sha256(input_bytes).hexdigest():raise ValueError('Recognition image hash mismatch')
        response['orientation']=orientation_meta
        doc=response['document'];fields=doc['fields']
        amount, tx_date, missing, warnings = apply_post_extraction_checks(doc, orientation_meta, use_transaction_save_amount=True)
        classification=doc.get('classification') or {}
        final_status=classification.get('final_status')
        guide_message=classification.get('guide_message')

        if final_status=='unsupported':
            stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.COMPLETED,65,'문서 분석을 완료했습니다.')
            stage(OcrStage.TRANSACTION_EXTRACTION,OcrStageStatus.FAILED,80,guide_message or '지원하지 않는 문서입니다.')
            stage(OcrStage.MISSING_FIELD_CHECK,OcrStageStatus.SKIPPED,100,guide_message or '지원하지 않는 문서')
            return OcrPipelineResult(status='UNSUPPORTED',vendor=fields.get('vendor'),amount=int(amount) if amount is not None else None,transaction_date=tx_date,raw_text=json.dumps(response,ensure_ascii=False,separators=(',',':')),missing_fields=missing,warnings=[guide_message or '현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.'],pipeline_name='luna_low',pipeline_version=CONTRACT_VERSION,retention_status='under_review',doc_type=classification.get('doc_type'),support_status=classification.get('support_status'),issues=classification.get('issues',[]),affected_regions=classification.get('affected_regions',[]),issue_code=classification.get('issue_code'),guide_message=guide_message)

        if final_status=='retake':
            stage(OcrStage.PHOTO_QUALITY,OcrStageStatus.FAILED,20,guide_message or '사진 재촬영 필요')
            stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.FAILED,50,'사진 판독 문제로 글자 인식이 어렵습니다.')
            stage(OcrStage.TRANSACTION_EXTRACTION,OcrStageStatus.FAILED,80,'거래 정보를 확정할 수 없습니다.')
            stage(OcrStage.MISSING_FIELD_CHECK,OcrStageStatus.SKIPPED,100,guide_message or '다시 촬영해 주세요.')
            return OcrPipelineResult(status='RETAKE',vendor=fields.get('vendor'),amount=int(amount) if amount is not None else None,transaction_date=tx_date,raw_text=json.dumps(response,ensure_ascii=False,separators=(',',':')),missing_fields=missing,warnings=[guide_message or '사진 판독 문제로 주요 정보를 읽기 어렵습니다.'],pipeline_name='luna_low',pipeline_version=CONTRACT_VERSION,retention_status='under_review',doc_type=classification.get('doc_type'),support_status=classification.get('support_status'),issues=classification.get('issues',[]),affected_regions=classification.get('affected_regions',[]),issue_code=classification.get('issue_code'),guide_message=guide_message)

        stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.COMPLETED,65,'사진 문서 인식 응답을 받았습니다.')
        stage(OcrStage.TRANSACTION_EXTRACTION,OcrStageStatus.COMPLETED,80,'인쇄값·금액 역할·품목 구조를 보존했습니다.')
        stage(OcrStage.MISSING_FIELD_CHECK,OcrStageStatus.PROCESSING,85,'누락·후보 충돌·출력 구조를 확인하고 있습니다.')
        partial=bool(missing or warnings or final_status=='needs_edit')
        stage(OcrStage.MISSING_FIELD_CHECK,OcrStageStatus.FAILED if partial else OcrStageStatus.COMPLETED,100,'사용자 확인이 필요합니다.' if partial else '검사 완료. 자동 정답 확정을 의미하지 않습니다.')
        return OcrPipelineResult(status='NEEDS_EDIT' if final_status=='needs_edit' and classification.get('doc_type')!='uninspected' else 'PARTIAL' if partial else 'COMPLETED',vendor=fields.get('vendor'),amount=int(amount) if amount is not None else None,transaction_date=tx_date,raw_text=json.dumps(response,ensure_ascii=False,separators=(',',':')),missing_fields=missing,warnings=warnings[:50],pipeline_name='luna_low',pipeline_version=response.get('contract_version',CONTRACT_VERSION),retention_status='under_review',doc_type=classification.get('doc_type'),support_status=classification.get('support_status'),issues=classification.get('issues',[]),affected_regions=classification.get('affected_regions',[]),issue_code=classification.get('issue_code'),guide_message=guide_message)

def create_pipeline():return LunaLowPipeline()
