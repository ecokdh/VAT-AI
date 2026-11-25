"""빈 신고서 PDF 위에 값을 덧입힌다(reportlab으로 글자만 있는 페이지를 만들어 pypdf로 합친다).

학습용 training/vatform/fill.py와 같은 좌표·글자 배치를 쓴다. 둘이 달라지면 모델 검증이 틀어진다.
"""
import io
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from pypdf import PageObject, PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.vat_return.fields import FIELD_BY_ID, PAGE_HEIGHT, PAGE_WIDTH, REG_NO_DASH_CELLS, Field

ASSETS = Path(__file__).resolve().parent / "assets"
TEMPLATE = ASSETS / "vat_return_form21_2026.pdf"
LOGO = ASSETS / "vat-ai-logo.png"  # vat-ai-logo.svg(앱 시작 화면 로고)를 640px로 그린 투명 PNG
WATERMARK_OPACITY = 0.12  # 0~1. 칸에 적힌 값이 가려지지 않을 만큼 연하게.
FONT_NAME = "VatFormFont"
FONT_CANDIDATES = ("C:/Windows/Fonts/malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


def _register_font() -> None:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    path = next((p for p in (settings.VAT_FORM_FONT, *FONT_CANDIDATES) if p and Path(p).exists()), None)
    if path is None:
        raise RuntimeError("신고서에 쓸 한글 TTF 폰트가 없습니다. VAT_FORM_FONT에 폰트 경로를 지정해 주세요.")
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


def _overlay(draw: Callable[[canvas.Canvas], None]) -> PageObject:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    draw(c)
    c.showPage()  # 그린 것이 없어도 페이지 1장을 만들어 합칠 수 있게 한다.
    c.save()
    return PdfReader(buffer).pages[0]


def _stamp_page1(source: PdfReader, overlay: PageObject) -> bytes:
    """source의 1쪽에 overlay를 얹어 1쪽짜리 PDF로 돌려준다."""
    writer = PdfWriter()
    writer.add_page(source.pages[0]).merge_page(overlay)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def fill_page1(values: dict[str, str], template: Path = TEMPLATE) -> bytes:
    """values: {필드 id: 인쇄할 문자열}. 값을 채운 1쪽짜리 PDF를 돌려준다(2쪽 이후는 쓰지 않아 뺀다)."""
    _register_font()

    def draw(c: canvas.Canvas) -> None:
        for field_id, value in values.items():
            if value:
                _draw(c, FIELD_BY_ID[field_id], value)

    return _stamp_page1(PdfReader(template), _overlay(draw))


def _watermark_image() -> Image.Image:
    # 투명 배경 로고 전체를 WATERMARK_OPACITY만큼 연하게 만든다.
    logo = Image.open(LOGO).convert("RGBA")
    logo.putalpha(logo.getchannel("A").point(lambda v: round(v * WATERMARK_OPACITY)))
    return logo


def add_watermark(pdf: bytes) -> bytes:
    """제출용으로 쓰이지 않도록 1쪽 가운데에 VAT-AI 로고를 연하게 얹는다."""
    logo = _watermark_image()
    width = PAGE_WIDTH * 0.5
    height = width * logo.height / logo.width

    def draw(c: canvas.Canvas) -> None:
        c.drawImage(ImageReader(logo), (PAGE_WIDTH - width) / 2, (PAGE_HEIGHT - height) / 2, width, height, mask="auto")

    return _stamp_page1(PdfReader(io.BytesIO(pdf)), _overlay(draw))
