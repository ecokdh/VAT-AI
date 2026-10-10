# OCR 파이프라인 어댑터 계약

VAT-AI는 이미지 업로드·검증·저장, 비동기 작업, 결과 확인·사용자 확정 흐름을 소유합니다. OCR/문서 분석 로직은 `app.ocr_pipeline.contract.OcrPipeline` 어댑터 뒤에 두어 동료가 고도화한 구현으로 교체할 수 있게 합니다. 현재 기본 어댑터는 기존 CLOVA 추출기를 감싸며, 별도 구현이 설정되지 않으면 이를 사용합니다.

## 파이프라인 연결

```env
OCR_PIPELINE=team_ocr.adapter:create_pipeline
```

팩토리는 `process(request, report_progress)`를 제공하는 객체를 반환합니다.

```python
from datetime import date

from app.ocr_pipeline.contract import (
    OcrPipelineInput,
    OcrPipelineResult,
    OcrStage,
    OcrStageStatus,
    OcrStageUpdate,
)


class TeamOcrPipeline:
    def process(self, request: OcrPipelineInput, report_progress) -> OcrPipelineResult:
        report_progress(OcrStageUpdate(
            stage=OcrStage.PHOTO_QUALITY, status=OcrStageStatus.PROCESSING,
            progress_percent=10,
        ))
        # 팀 파이프라인 호출 및 자체 응답 정규화
        output = self.client.analyze(request.image_bytes, request.content_type)
        report_progress(OcrStageUpdate(
            stage=OcrStage.PHOTO_QUALITY, status=OcrStageStatus.COMPLETED,
            progress_percent=20,
        ))
        # 각 단계마다 실제 상태와 진행률을 callback으로 알려줍니다.
        return OcrPipelineResult(
            status="PARTIAL" if output.missing_fields else "COMPLETED",
            vendor=output.vendor,
            amount=output.total_amount,
            transaction_date=output.date,
            raw_text=output.ocr_text,
            field_confidences=output.confidences,
            missing_fields=output.missing_fields,
            warnings=output.warnings,
            pipeline_name="team-ocr",
            pipeline_version="2.3.0",
        )


def create_pipeline() -> TeamOcrPipeline:
    return TeamOcrPipeline()
```

## 공통 진행 단계

작업 진행은 `photo_quality` → `text_recognition` → `transaction_extraction` → `missing_field_check` 순서입니다. 각 단계 상태는 `pending`, `processing`, `completed`, `failed`, `skipped` 중 하나입니다. callback은 `OcrStageUpdate(stage, status, progress_percent, message)`로 단계와 사용자에게 표시할 문구를 전달하며, 진행 상태는 DB에 저장되어 v2 영수증 조회 응답으로 제공됩니다.

`OcrPipelineInput`은 계약 버전, 영수증 ID, MIME 형식, 이미지 바이트를 포함합니다. 결과 `OcrPipelineResult`는 처리 상태, 거래처, 총액, 거래일, OCR 원문, 필드별 신뢰도, 누락 필드, 경고, 파이프라인 이름·버전, 보존 상태(`required`/`not_required`/`under_review`)를 반환합니다. OCR 원문은 최대 40,000자입니다. 미인식 필드는 `PARTIAL`로 반환해 사용자가 매입 보관함으로 이동하기 전에 추출 확인 화면에서 직접 입력·수정할 수 있습니다. 보존 상태를 분류하지 못하면 `under_review`로 두며 영구 삭제 요청을 막습니다. OCR 실패 시에는 같은 저장 사진으로 사용자 재시도 1회를 허용하고, 백그라운드 작업 자체의 일시 장애는 작업 재시도 대상입니다.

사용자 흐름은 `업로드 → OCR 결과 확인·누락 정보 보완 → 확인 후 매입 보관함 → 별도 거래 정보 확인·저장 → 메인 화면`입니다. 추출 확인은 거래 확정이 아니며, 이 과정에서 공제 분석을 자동 실행하지 않습니다. 분석 어댑터와 OCR 어댑터는 독립적으로 교체할 수 있습니다. OCR 결과를 사용자 확인 없이 확정 거래나 공제 판단으로 바꾸지 않습니다.
