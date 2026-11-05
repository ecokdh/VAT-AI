"""학습한 신고서 읽기 모델을 HTTP로 여는 검증 서버. GPU 서버(DGX Spark)에서 실행한다.

    uvicorn serve:app --host 127.0.0.1 --port 8001

앱(app/vat_form/verifier.py)은 신고서 1쪽 PNG를 POST /read로 보내고, 칸별 값 JSON을 받는다.
공유 서버라 127.0.0.1로만 열고, 이 PC에서는 SSH 터널(ssh -L 8001:localhost:8001 dgx-spark)로 접속한다.
"""
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from fastapi import FastAPI, File, UploadFile
from peft import PeftModel
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

from evaluate import parse_json
from vatform.prompts import READ_PROMPT, user_message

BASE_MODEL = os.environ.get("FORM_BASE_MODEL", "Qwen/Qwen3-VL-4B-Instruct")
ADAPTER = Path(os.environ.get("FORM_ADAPTER", "outputs/qwen3vl4b-lora/adapter"))
state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    state["processor"] = AutoProcessor.from_pretrained(BASE_MODEL)
    base = Qwen3VLForConditionalGeneration.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, device_map="auto")
    state["model"] = PeftModel.from_pretrained(base, ADAPTER).eval()
    yield
    state.clear()


app = FastAPI(title="VAT-AI form reader", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ready": "model" in state, "base_model": BASE_MODEL, "adapter": str(ADAPTER)}


@app.post("/read")
def read(image: UploadFile = File(...)):
    processor, model = state["processor"], state["model"]
    picture = Image.open(io.BytesIO(image.file.read())).convert("RGB")
    text = processor.apply_chat_template([user_message(READ_PROMPT)], tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], images=[picture], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
    raw = processor.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
    values = parse_json(raw)
    return {"values": values if isinstance(values, dict) else {}, "raw": raw}
