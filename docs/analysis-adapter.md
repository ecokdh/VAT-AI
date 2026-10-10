# 매입 공제 분석 모델 어댑터 계약

VAT-AI는 모델 개발·법령 판단 로직을 `app.analysis.contract.PurchaseAnalyzer` 뒤로 분리합니다. 동료가 만든 모델은 이 계약에 맞춘 Python 어댑터로 연결합니다. 어댑터는 거래 사실을 판정하고 근거와 설명을 돌려주며, 세액 금액을 계산하지 않습니다.

## 연결 방법

`module:factory` 형식의 서버 설정을 지정합니다.

```env
DEDUCTION_ANALYZER=team_model.adapter:create_analyzer
```

팩토리는 `analyze(request)` 메서드를 가진 객체를 반환해야 합니다.

```python
from app.analysis.contract import AnalysisDecision, AnalysisRequest, LegalReference


class TeamAnalyzer:
    def analyze(self, request: AnalysisRequest) -> AnalysisDecision:
        # 여기서 팀 모델의 요청·응답 형식을 VAT-AI 계약으로 변환합니다.
        model_output = self.model.predict(request.model_dump(mode="json"))
        return AnalysisDecision(
            disposition=model_output["disposition"],
            reason=model_output["reason"],
            missing_information=model_output.get("missing_information", []),
            legal_references=[LegalReference.model_validate(ref) for ref in model_output.get("legal_references", [])],
            analyzer_name="team-model",
            analyzer_version="1.4.0",
            knowledge_version="vat-rules-2026-01",
        )


def create_analyzer() -> TeamAnalyzer:
    return TeamAnalyzer()
```

## 입력과 출력

입력 `AnalysisRequest`에는 `contract_version`, 작업 ID, 거래 ID·revision·일자·거래처·금액·증빙·사용자 확인 여부, 연결된 영수증의 OCR 원문(최대 40,000자, 없을 수 있음), 사업자 확인 상태·과세유형·확인된 업종/사업 기간 정보가 포함됩니다. 비밀키와 사용자 로그인 정보는 전달하지 않습니다.

출력 판정은 아래 네 값 중 하나입니다.

| 판정 | 서비스 처리 |
|---|---|
| `DEDUCTIBLE` | 근거가 있으면 분석 완료. 계산 엔진이 증빙·과세유형 규칙을 확인해 금액 산출 |
| `NOT_DEDUCTIBLE` | 공제 집계에서 제외 |
| `NEEDS_REVIEW` | CAUTION으로 표시하고 공제 계산에서 제외 |
| `INSUFFICIENT_INFO` | 미계산 처리. 추가 확인이 필요한 필드명을 `missing_information`에 반환 |

`legal_references` 항목은 `source_id`, `title`, 선택값인 `locator`, `url`, `effective_date`로 구성합니다. `DEDUCTIBLE` 또는 `NOT_DEDUCTIBLE`인데 근거가 비어 있으면 서비스가 자동으로 `NEEDS_REVIEW` 처리합니다. 모델 응답에는 공제액/세액 필드를 넣지 마세요. 계약 검증이 이를 거부하며 작업은 실패·재시도됩니다.

계약 변경은 `contract_version`을 올리는 별도 버전 변경으로 관리합니다. 팀 모델 자체의 버전과 근거 자료 버전은 매 결과에 함께 기록해 재현성과 검토 이력을 확보합니다.
