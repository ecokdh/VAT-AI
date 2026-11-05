"""신고서 1쪽을 모델 검증용 이미지로 바꾼다. 학습 데이터(training/make_dataset.py)와 같은 크기·색으로 만든다."""
import io

import pypdfium2 as pdfium

from app.vat_return.fields import PAGE_HEIGHT, PAGE_WIDTH

VERIFY_WIDTH = 1280  # 학습 때 쓴 가로 크기(px). 바꾸면 모델 정확도가 달라진다.


def page1_png(pdf: bytes, width: int = VERIFY_WIDTH) -> bytes:
    height = round(width * PAGE_HEIGHT / PAGE_WIDTH / 32) * 32
    page = pdfium.PdfDocument(pdf)[0]
    image = page.render(scale=width / PAGE_WIDTH).to_pil().convert("L").resize((width, height))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
