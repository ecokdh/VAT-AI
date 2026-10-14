"""Portable review PDF when wkhtmltopdf is unavailable on a QA machine."""
from html import escape
from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def render_review_pdf(snapshot: dict) -> bytes:
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    font = "VATKorean" if font_path.exists() else "HYSMyeongJo-Medium"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(font_path)) if font_path.exists() else UnicodeCIDFont(font))
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="VAT-AI 신고 지원 자료", leftMargin=42, rightMargin=42)
    body = ParagraphStyle("body", fontName=font, fontSize=10, leading=17, wordWrap="CJK", spaceAfter=10)
    title = ParagraphStyle("title", parent=body, fontSize=22, leading=30, textColor=colors.HexColor("#3f50ed"), spaceAfter=22)
    parts = [Paragraph("VAT-AI 신고 지원 자료", title), Paragraph(escape(str(snapshot.get("period", ""))), body),
        Paragraph("이 자료는 확정한 거래와 검토 결과를 정리한 참고 자료이며, 세무 신고서가 아닙니다. 실제 제출 전 내용을 확인해 주세요.", body), Spacer(1,16)]
    labels = [("output_vat","매출세액"),("eligible_input_vat","일반 매입 공제액"),("deemed_input_vat","의제매입 공제액"),("payable_estimate","예상 납부세액")]
    rows = [[label, "확인 필요" if snapshot.get(key) is None else f"{snapshot[key]:,}원"] for key,label in labels]
    table = Table(rows, colWidths=[300, 170])
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),font),("FONTSIZE",(0,0),(-1,-1),11),
        ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#eef3ff")),("GRID",(0,0),(-1,-1),.5,colors.HexColor("#dce3ee")),
        ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14)]))
    parts.extend([table,Spacer(1,24)])
    for note in snapshot.get("notes",[]):
        parts.append(Paragraph(escape(str(note)),body))
    document.build(parts)
    return buffer.getvalue()
