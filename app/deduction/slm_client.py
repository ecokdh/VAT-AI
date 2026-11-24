"""공제 1차 판정 sLLM 호출. 분류 그래프의 slm_judge 노드가 사용한다.

모델(Qwen3-4B LoRA)은 서버(training/deduction/serve_slm.py)에서 돌고, 여기서는 LLM과 같은 지시문·입력을 보내 판정과 신뢰도를 받는다.
DEDUCTION_SLM_URL이 비어 있으면 sLLM을 쓰지 않는다.
"""

import httpx

from app.core.config import settings
from app.deduction.analyzer import AnalysisRequest
from app.deduction.graph import prompts
from app.deduction.graph.state import JudgeOutput
from app.deduction.rag.schemas import LawOut


class RemoteSlm:
    def __init__(self, url: str, timeout: float):
        self.url, self.timeout = url.rstrip("/"), timeout

    def __call__(self, request: AnalysisRequest, laws: list[LawOut]) -> tuple[JudgeOutput, float | None]:
        body = {"system": prompts.INSTRUCTIONS, "prompt": prompts.build_input(request, laws, [])}
        response = httpx.post(f"{self.url}/judge", json=body, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result.get("output"), dict):
            raise ValueError("sLLM 응답을 해석하지 못했습니다.")
        return JudgeOutput.model_validate(result["output"]), result.get("confidence")


def load_slm() -> RemoteSlm | None:
    url = settings.DEDUCTION_SLM_URL
    return RemoteSlm(url, settings.DEDUCTION_SLM_TIMEOUT_SECONDS) if url else None
