"""빈 신고서 PDF 위에 값을 덧입힌다(reportlab으로 글자만 있는 페이지를 만들어 pypdf로 합친다)."""
import io
import os
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .fields import FIELD_BY_ID, PAGE_HEIGHT, PAGE_WIDTH, REG_NO_DASH_CELLS, Field

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "vat_return_form21_2026.pdf"
FONT_NAME = "VatFormFont"
FONT_CANDIDATES = (os.environ.get("VAT_FORM_FONT", ""), "C:/Windows/Fonts/malgun.ttf",
                   "/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


def _register_font() -> None:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    path = next((p for p in FONT_CANDIDATES if p and Path(p).exists()), None)
    if path is None:
        raise FileNotFoundError("한글 TTF 폰트가 필요합니다. VAT_FORM_FONT 환경변수로 경로를 지정해 주세요.")
    pdfmetrics.registerFont(TTFont(FONT_NAME, path))


def _baseline(field: Field) -> float:
    # 칸 세로 가운데에 글자가 오도록 기준선을 잡는다(reportlab은 왼쪽 아래가 원점).
    _, top, _, bottom = field.box
    return PAGE_HEIGHT - (top + bottom) / 2 - field.size * 0.35


def _draw(c: canvas.Canvas, field: Field, value: str) -> None:
    x0, _, x1, _ = field.box
    y = _baseline(field)
    c.setFont(FONT_NAME, field.size)
    if field.kind == "amount":
        c.drawRightString(x1 - 3, y, value)
    elif field.kind == "check":
        c.drawCentredString((x0 + x1) / 2, y, value)
    elif field.kind == "digits":
        width = (x1 - x0) / field.cells
        cells = [i for i in range(field.cells) if field.id != "biz.reg_no" or i not in REG_NO_DASH_CELLS]
        for i, ch in zip(cells, value.replace("-", "")):
            c.drawCentredString(x0 + width * (i + 0.5), y, ch)
    else:
        c.drawString(x0 + 2, y, value)


def fill_page1(values: dict[str, str], template: Path = TEMPLATE) -> bytes:
    """values: {필드 id: 인쇄할 문자열}. 1쪽만 채운 6쪽 PDF를 돌려준다."""
    _register_font()
    overlay = io.BytesIO()
    c = canvas.Canvas(overlay, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    for field_id, value in values.items():
        if value:
            _draw(c, FIELD_BY_ID[field_id], value)
    c.showPage()  # 빈 양식(값 없음)도 페이지 1장을 만들어 합칠 수 있게 한다.
    c.save()

    writer = PdfWriter(clone_from=PdfReader(template))
    writer.pages[0].merge_page(PdfReader(overlay).pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
