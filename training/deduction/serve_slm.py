"""학습한 공제 판정 sLLM을 HTTP로 여는 판정 서버. GPU 서버(DGX Spark)에서 실행한다.

    uvicorn serve_slm:app --host 127.0.0.1 --port 8002

POST /judge {"system": 지시문, "prompt": 거래·조문 입력} → {"output": JudgeOutput dict | null, "confidence", "seconds", "raw"}
앱은 지금 gpt에 보내는 것과 같은 지시문(prompts.INSTRUCTIONS)과 입력(prompts.build_input)을 그대로 보낸다.
공유 서버라 127.0.0.1로만 열고, 이 PC에서는 VS Code 포트 전달(또는 ssh -L 8002:localhost:8002 dgx-spark)로 접속한다.
"""
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from fastapi import FastAPI
from peft import PeftModel
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from evaluate_slm import parse, verdict_confidence

BASE_MODEL = os.environ.get("SLM_BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507")
ADAPTER = Path(os.environ.get("SLM_ADAPTER", "outputs/qwen3-4b-deduction/adapter"))
state: dict = {}
gpu = threading.Lock()  # 모델 하나를 여러 요청이 동시에 쓰지 않게 한 건씩 처리한다.


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["tokenizer"] = AutoTokenizer.from_pretrained(ADAPTER)
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, attn_implementation="sdpa", device_map="cuda")
    state["model"] = PeftModel.from_pretrained(base, ADAPTER).eval()
    yield
    state.clear()


app = FastAPI(title="VAT-AI deduction sLLM", lifespan=lifespan)


class JudgeRequest(BaseModel):
    system: str
    prompt: str


@app.get("/health")
def health():
    return {"ready": "model" in state, "base_model": BASE_MODEL, "adapter": str(ADAPTER)}


@app.post("/judge")
def judge(request: JudgeRequest):
    tokenizer, model = state["tokenizer"], state["model"]
    messages = [{"role": "system", "content": request.system}, {"role": "user", "content": request.prompt}]
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True).to(model.device)
    started = time.perf_counter()
    with gpu, torch.no_grad():
        generated = model.generate(**inputs, max_new_tokens=1024, do_sample=False,
                                   return_dict_in_generate=True, output_scores=True)
    token_ids = generated.sequences[0][inputs["input_ids"].shape[1]:].tolist()
    raw = tokenizer.decode(token_ids, skip_special_tokens=True)
    output = parse(raw)
    return {
        "output": output if isinstance(output, dict) else None,
        "confidence": verdict_confidence(tokenizer, token_ids, generated.scores),
        "seconds": round(time.perf_counter() - started, 2),
        "raw": raw,
    }
