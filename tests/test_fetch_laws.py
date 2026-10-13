from app.deduction.rag import fetch_laws
from app.deduction.rag.fetch_laws import split_articles


def article(number, content, paragraphs=None, branch=None):
    unit = {"조문번호": number, "조문여부": "조문", "조문내용": content}
    if paragraphs is not None:
        unit["항"] = paragraphs
    if branch:
        unit["조문가지번호"] = branch
    return unit


def law(*units):
    return {"조문": {"조문단위": list(units)}}


def test_splits_by_paragraph_and_drops_deleted_and_history():
    result = split_articles("부가가치세법", law(
        {"조문번호": "1", "조문여부": "전문", "조문내용": "제1장 총칙"},
        article("30", "제30조(세율) 부가가치세의 세율은 10퍼센트로 한다."),
        article("31", "제31조 삭제"),
        article("39", "제39조(공제하지 아니하는 매입세액)", [
            {"항내용": "① 다음 각 호의 매입세액은 공제하지 아니한다. <개정 2017.12.19>",
             "호": [{"호내용": "3. 삭제<2014.1.1>"}, {"호내용": "4. 사업과 직접 관련이 없는 지출"}]},
            {"항내용": "② 삭제"},
        ]),
        article("3", "제3조의2(신탁)", [{"항내용": "① 내용"}, {"항내용": "② 내용"}], branch="2"),
    ))

    assert [(law.article, law.content) for law in result] == [
        ("제30조", "제30조(세율) 부가가치세의 세율은 10퍼센트로 한다."),
        ("제39조 제1항", "제39조(공제하지 아니하는 매입세액)\n① 다음 각 호의 매입세액은 공제하지 아니한다.\n4. 사업과 직접 관련이 없는 지출"),
        ("제3조의2 제1항", "제3조의2(신탁)\n① 내용"),
        ("제3조의2 제2항", "제3조의2(신탁)\n② 내용"),
    ]


def test_long_paragraph_is_chunked_and_table_borders_removed(monkeypatch):
    monkeypatch.setattr(fetch_laws, "MAX_CHARS", 60)
    result = split_articles("부가가치세법 시행령", law(
        article("8", "제8조(사업장)", [
            {"항내용": "① 범위는 다음 표와 같다.┌────┬────┐│사업    │범위    │",
             "호": [{"호내용": f"{n}. " + "가" * 20} for n in range(1, 4)]},
        ]),
    ))

    assert [law.article for law in result] == ["제8조 (1/2)", "제8조 (2/2)"]
    assert all(len(law.content) <= 60 for law in result)
    assert "─" not in result[0].content and "| 사업 | 범위 |" in result[0].content
