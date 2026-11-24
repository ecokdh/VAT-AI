"""팀원이 학습한 매입 영수증 Qwen LoRA 두 개를 OpenAI 호환 API로 여는 서버. GPU 서버(DGX Spark)에서 실행한다.

    uvicorn serve_receipt_ocr:app --host 127.0.0.1 --port 8003

앱(app/receipts/ocr/qwen.py)은 {BASE_URL}/chat/completions로 요청하고, 요청의 model 이름으로 두 모델을 고른다.
- vat-receipt-qwen-ocr        : Qwen3-4B-Instruct-2507 + qwen3-4b-ocr-adapter (CLOVA OCR 글자·좌표 → JSON)
- vat-receipt-qwen-vl-step087 : Qwen3-VL-8B-Instruct + qwen3-vl-8b-photo-ocr-adapter (사진 + OCR → JSON)
그래서 이 PC .env의 QWEN_OCR_BASE_URL과 QWEN_PHOTO_OCR_BASE_URL을 둘 다 http://localhost:8003/v1 로 둔다.

OCR_LOAD=text 또는 photo로 한쪽만 올릴 수 있다(메모리가 부족할 때). 공유 서버라 127.0.0.1로만 연다.
"""
import base64
import io
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import torch
from fastapi import FastAPI, Header, HTTPException
from peft import PeftModel
from PIL import Image
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoProcessor, AutoTokenizer, Qwen3VLForConditionalGeneration

MODELS_DIR = Path(os.environ.get("OCR_MODELS_DIR", Path.home() / "vat-ai-dong" / "models"))
TEXT = {"name": os.environ.get("OCR_TEXT_NAME", "vat-receipt-qwen-ocr"),
        "base": "Qwen/Qwen3-4B-Instruct-2507", "adapter": MODELS_DIR / "qwen3-4b-ocr-adapter"}
PHOTO = {"name": os.environ.get("OCR_PHOTO_NAME", "vat-receipt-qwen-vl-step087"),
         "base": "Qwen/Qwen3-VL-8B-Instruct", "adapter": MODELS_DIR / "qwen3-vl-8b-photo-ocr-adapter"}
LOAD = set(os.environ.get("OCR_LOAD", "text,photo").split(","))
API_KEY = os.environ.get("OCR_API_KEY", "")  # 비우면 인증 없이 받는다(127.0.0.1 전용)
MAX_NEW_TOKENS = 4096

state: dict = {}
gpu = threading.Lock()  # 한 번에 한 건씩 생성한다.


@asynccontextmanager
async def lifespan(_: FastAPI):
    if "text" in LOAD:
        base = AutoModelForCausalLM.from_pretrained(TEXT["base"], dtype=torch.bfloat16, device_map="cuda")
        state[TEXT["name"]] = ("text", AutoTokenizer.from_pretrained(TEXT["adapter"]),
                               PeftModel.from_pretrained(base, TEXT["adapter"]).eval())
    if "photo" in LOAD:
        base = Qwen3VLForConditionalGeneration.from_pretrained(PHOTO["base"], dtype=torch.bfloat16, device_map="cuda")
        state[PHOTO["name"]] = ("photo", AutoProcessor.from_pretrained(PHOTO["adapter"]),
                                PeftModel.from_pretrained(base, PHOTO["adapter"]).eval())
    yield
    state.clear()


app = FastAPI(title="VAT-AI receipt OCR (Qwen LoRA)", lifespan=lifespan)


class ChatRequest(BaseModel):
    model: str
    messages: list[dict]
    max_tokens: int | None = None
    temperature: float | None = None  # 항상 탐욕적 생성(temperature 0)으로 처리한다.


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") for part in content if part.get("type") == "text")


def image_of(url: str) -> Image.Image:
    if not url.startswith("data:"):
        raise HTTPException(400, "이미지는 data URL(base64)만 받습니다.")
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def photo_inputs(processor, messages: list[dict]):
    """OpenAI 형식(image_url)을 Qwen3-VL 형식으로 바꾼다. 이미지 자체는 processor에 따로 넘긴다."""
    converted, images = [], []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            converted.append({"role": message["role"], "content": [{"type": "text", "text": content}]})
            continue
        parts = []
        for part in content:
            if part.get("type") == "image_url":
                images.append(image_of(part["image_url"]["url"]))
                parts.append({"type": "image"})
            elif part.get("type") == "text":
                parts.append({"type": "text", "text": part["text"]})
        converted.append({"role": message["role"], "content": parts})
    text = processor.apply_chat_template(converted, tokenize=False, add_generation_prompt=True)
    return processor(text=[text], images=images or None, return_tensors="pt")


@app.get("/health")
def health():
    return {"ready": bool(state), "models": list(state), "models_dir": str(MODELS_DIR)}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": name, "object": "model"} for name in state]}


@app.post("/v1/chat/completions")
def chat_completions(request: ChatRequest, authorization: str | None = Header(default=None)):
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(401, "인증 키가 맞지 않습니다.")
    if request.model not in state:
        raise HTTPException(404, f"모델 '{request.model}'이(가) 이 서버에 없습니다. 있는 모델: {list(state)}")
    kind, tokenizer_or_processor, model = state[request.model]
    if kind == "text":
        messages = [{"role": m["role"], "content": text_of(m["content"])} for m in request.messages]
        inputs = tokenizer_or_processor.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        tokenizer = tokenizer_or_processor
    else:
        inputs = photo_inputs(tokenizer_or_processor, request.messages)
        tokenizer = tokenizer_or_processor.tokenizer

    limit = min(request.max_tokens or MAX_NEW_TOKENS, MAX_NEW_TOKENS)
    started = time.perf_counter()
    with gpu, torch.no_grad():
        output = model.generate(**inputs.to(model.device), max_new_tokens=limit, do_sample=False)
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    # 끝 토큰을 만나 멈췄으면 한도보다 짧다. 한도까지 찼으면 답이 잘린 것이라 앱이 결과를 버린다.
    finish_reason = "length" if len(new_tokens) >= limit else "stop"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": tokenizer.decode(new_tokens, skip_special_tokens=True)},
            "finish_reason": finish_reason,
        }],
        "usage": {"prompt_tokens": inputs["input_ids"].shape[1], "completion_tokens": len(new_tokens),
                  "seconds": round(time.perf_counter() - started, 2)},
    }
