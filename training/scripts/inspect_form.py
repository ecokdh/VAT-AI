"""양식이 개정됐을 때 vatform/fields.py 좌표를 다시 잡기 위한 도구.
1쪽의 글자 위치(W)와 표 선(V: 세로선, H: 가로선)을 PDF 포인트 단위로 출력한다.

    python training/scripts/inspect_form.py training/assets/vat_return_form21_2026.pdf > form_geometry.txt
"""
import sys

import pdfplumber

with pdfplumber.open(sys.argv[1]) as pdf:
    page = pdf.pages[0]
    print("page", page.width, page.height)
    for w in page.extract_words():
        print(f"W {w['x0']:.1f} {w['top']:.1f} {w['x1']:.1f} {w['bottom']:.1f} {w['text']}")
    for e in page.edges:
        if e["orientation"] == "v" and e["height"] > 4:
            print(f"V x={e['x0']:.1f} y={e['top']:.1f}-{e['bottom']:.1f}")
        elif e["orientation"] == "h" and e["width"] > 4:
            print(f"H y={e['top']:.1f} x={e['x0']:.1f}-{e['x1']:.1f}")
