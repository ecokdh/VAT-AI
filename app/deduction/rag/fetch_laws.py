"""국가법령정보 공동활용 API에서 현행법령(시행일 기준) 본문을 받아 항 단위 조문으로 저장한다.

실행: python -m app.deduction.rag.fetch_laws
결과: data/laws.json — 각 항목이 POST /rag/embed 요청 본문(LawEmbedIn) 형식이다.
"""

import json
import re
from pathlib import Path

import httpx

from app.core.config import settings
from app.deduction.rag.schemas import LawEmbedIn


LAW_IDS = {
    "001571": "부가가치세법",
    "003666": "부가가치세법 시행령",
    "007289": "부가가치세법 시행규칙",
}
API_URL = "https://www.law.go.kr/DRF/lawService.do"
OUTPUT_PATH = Path("data/laws.json")
# 이보다 긴 항은 호 단위(호가 없으면 공백 경계)로 나눈다. 임베딩 입력 한도와 검색 정확도를 위해서다.
MAX_CHARS = 3000

# "<개정 2017.12.19>" 같은 개정 이력 표기와 <img> 태그. 검색에는 잡음이라 지운다.
HISTORY = re.compile(r"\s*<[^>]*>")
TABLE_BORDER = re.compile(r"[─━┌┐└┘├┤┬┴┼]+")


def fetch_law(law_id: str) -> dict:
    response = httpx.get(
        API_URL,
        params={"OC": settings.LAW_OC, "target": "eflaw", "type": "JSON", "ID": law_id},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if "법령" not in data:
        raise RuntimeError(f"법령 {law_id} 조회 실패: {data}")
    return data["법령"]


def split_articles(source: str, law: dict) -> list[LawEmbedIn]:
    laws = []
    for article in _as_list(law["조문"]["조문단위"]):
        if article.get("조문여부") != "조문":  # 장·절 제목
            continue
        heading = _clean(article["조문내용"])
        if _is_deleted(heading):
            continue

        label = f"제{article['조문번호']}조" + (f"의{article['조문가지번호']}" if article.get("조문가지번호") else "")
        paragraphs = _as_list(article.get("항"))
        if not paragraphs:
            laws.append(LawEmbedIn(source=source, article=label, content=heading))
            continue

        for number, paragraph in enumerate(paragraphs, start=1):
            lead, items = _paragraph_parts(paragraph)
            if not lead and not items:
                continue
            article_label = f"{label} 제{number}항" if len(paragraphs) > 1 else label
            limit = MAX_CHARS - len(heading)
            units = [piece for text in (lead, *items) if text for piece in _wrap(text, limit)]
            chunks = _chunk(units, limit)
            for index, chunk in enumerate(chunks, start=1):
                suffix = f" ({index}/{len(chunks)})" if len(chunks) > 1 else ""
                content = "\n".join((heading, *chunk))
                laws.append(LawEmbedIn(source=source, article=article_label + suffix, content=content))

    return laws


def _paragraph_parts(paragraph: dict) -> tuple[str, list[str]]:
    """항 본문 한 줄과, 호(목 포함)별 텍스트 목록."""
    lead = _clean(paragraph.get("항내용", ""))
    items = []
    for item in _as_list(paragraph.get("호")):
        lines = [_clean(item.get("호내용", ""))]
        lines += [_clean(sub.get("목내용", "")) for sub in _as_list(item.get("목"))]
        text = "\n".join(line for line in lines if line and not _is_deleted(line))
        if text:
            items.append(text)
    return ("" if _is_deleted(lead) else lead), items


def _chunk(units: list[str], limit: int) -> list[list[str]]:
    """항 본문과 호를 순서대로 묶되 묶음 길이가 limit를 넘지 않게 한다."""
    chunks, current, size = [], [], 0
    for unit in units:
        if current and size + len(unit) > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(unit)
        size += len(unit)
    return chunks + [current] if current else chunks


def _wrap(text: str, limit: int) -> list[str]:
    """호 없이 표만 긴 항처럼 한 덩어리가 limit를 넘으면 공백 경계에서 자른다."""
    pieces = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        cut = cut if cut > 0 else limit
        pieces.append(text[:cut].strip())
        text = text[cut:].strip()
    return pieces + [text] if text else pieces


def _clean(text) -> str:
    if isinstance(text, list):  # 내용이 여러 줄이면 리스트로 온다.
        text = "\n".join(str(t) for t in text)
    text = HISTORY.sub("", str(text))
    # 박스 문자로 그린 표: 테두리는 지우고 칸 구분(│)만 남긴 뒤 칸 채움 공백을 줄인다.
    text = TABLE_BORDER.sub(" ", text).replace("│", " | ")
    return re.sub(r"[ \t　]{2,}", " ", text).strip()


def _is_deleted(text: str) -> bool:
    # "3. 삭제", "③ 삭제", "제5조 삭제" 처럼 번호 뒤가 '삭제'뿐인 줄
    return re.fullmatch(r"(제\d+조(의\d+)?|\S+)?\s*삭제", text) is not None


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def main() -> None:
    if not settings.LAW_OC:
        raise SystemExit(".env에 LAW_OC를 설정하세요.")

    laws = []
    for law_id, source in LAW_IDS.items():
        articles = split_articles(source, fetch_law(law_id))
        print(f"{source}: {len(articles)}개 조문")
        laws += articles

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps([law.model_dump() for law in laws], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"총 {len(laws)}개 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
