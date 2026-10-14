"""Latest MVP worker adapter for the tested direct-image Luna low contract."""
import asyncio,hashlib,json,re
from datetime import date
from app.ocr_pipeline.contract import OcrPipelineResult,OcrStage,OcrStageStatus,OcrStageUpdate
from app.receipts import luna_client
from app.receipts.luna_low_contract import CONTRACT_VERSION

async def recognize(image_bytes: bytes, mime_type: str = "image/jpeg"):
    return await luna_client.recognize(image_bytes, mime_type)

class LunaLowPipeline:
    def process(self,request,report_progress):
        def stage(s,state,n,message):report_progress(OcrStageUpdate(stage=s,status=state,progress_percent=n,message=message))
        stage(OcrStage.PHOTO_QUALITY,OcrStageStatus.SKIPPED,15,'사진 파일을 확인했습니다.')
        stage(OcrStage.TEXT_RECOGNITION,OcrStageStatus.PROCESSING,25,'원본 사진에서 글자·거래 정보를 함께 읽고 있습니다.')
        stage(OcrStage.TRANSACTION_EXTRACTION,OcrStageStatus.PROCESSING,30,'문서 인식 모델이 금액 역할과 상품 행을 함께 추출하고 있습니다.')
        try:response=asyncio.run(recognize(request.image_bytes,request.content_type))
        except luna_client.LunaFailure as exc:
            for s in [OcrStage.TEXT_RECOGNITION,OcrStage.TRANSACTION_EXTRACTION,OcrStage.MISSING_FIELD_CHECK]:stage(s,OcrStageStatus.FAILED,30,'문서 인식 실패: '+exc.code)
            return OcrPipelineResult(status='FAILED',raw_text=json.dumps({'engine':'luna_low','error_code':exc.code,'confirmed':False}),warnings=['문서 인식 실패: '+exc.code],missing_fields=['vendor','amount','transaction_date'],pipeline_name='luna_low',pipeline_version=CONTRACT_VERSION,doc_type=None,support_status=None,issues=[],affected_regions=[],issue_code=exc.code,guide_message='통신 또는 일시적인 처리 오류로 분석을 완료하지 못했습니다.')
        if response['image_sha256']!=hashlib.sha256(request.image_bytes).hexdigest():raise ValueError('Recognition image hash mismatch')
        doc=response['document'];fields=doc['fields'];warnings=[*doc['uncertain'],*['금액 후보 충돌: '+k for k in doc['conflicts']]]
        classification=doc.get('classification') or {}
        final_status=classification.get('final_status')
        guide_message=classification.get('guide_message')

        amount=fields.get('payment_amount')
        if amount is not None and (amount<0 or amount!=int(amount)):
            warnings.append('음수·소수 금액은 현재 MVP 정수 거래 계약에서 직접 확정할 수 없습니다. 인쇄값은 상세 결과에 보존했습니다.');amount=None
        tx_date=None;match=re.search(r'(20\d{2})[-./](\d{1,2})[-./](\d{1,2})',str(fields.get('transaction_datetime') or ''))
        if match:
            try:tx_date=date(*map(int,match.groups()))
            except ValueError:warnings.append('유효하지 않은 거래일입니다.')
        missing=[k for k,v in [('vendor',fields.get('vendor')),('amount',amount),('transaction_date',tx_date)] if v is None or v=='']

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
        return OcrPipelineResult(status='NEEDS_EDIT' if final_status=='needs_edit' and classification.get('doc_type')!='uninspected' else 'PARTIAL' if partial else 'COMPLETED',vendor=fields.get('vendor'),amount=int(amount) if amount is not None else None,transaction_date=tx_date,raw_text=json.dumps(response,ensure_ascii=False,separators=(',',':')),missing_fields=missing,warnings=warnings[:50],pipeline_name='luna_low',pipeline_version=CONTRACT_VERSION,retention_status='under_review',doc_type=classification.get('doc_type'),support_status=classification.get('support_status'),issues=classification.get('issues',[]),affected_regions=classification.get('affected_regions',[]),issue_code=classification.get('issue_code'),guide_message=guide_message)

def create_pipeline():return LunaLowPipeline()
