"""학습용 가상 신고서 값. 실제 사업자·개인 정보는 쓰지 않고, 금액은 양식의 계산식을 그대로 따른다."""
import random

SURNAMES = "김이박최정강조윤장임한오서신권황안송류홍"
GIVEN = "민서준하윤지도현수예린우진아율호연"
NAME_HEAD = ["카페", "베이커리", "식당", "분식", "공방", "서점", "꽃집", "스튜디오", "커피", "제과"]
NAME_TAIL = ["느린오후", "햇살", "온기", "바람", "소풍", "하루", "달빛", "모퉁이", "골목", "숲길"]
REGIONS = [("서울특별시", ["마포구", "종로구", "성동구", "관악구"]), ("경기도 수원시", ["영통구", "팔달구"]),
           ("부산광역시", ["해운대구", "수영구"]), ("대전광역시", ["유성구", "서구"])]
ROADS = ["월드컵로", "대학로", "성수이로", "광교중앙로", "해운대로", "대덕대로"]
# 업태·종목 칸이 좁아서 짧은 표기만 쓴다.
BIZ_TYPES = [("음식점업", "커피"), ("음식점업", "한식"), ("소매업", "서적"), ("제조업", "제과"), ("서비스업", "사진")]


def _won(rng: random.Random, lo: float, hi: float) -> int:
    return rng.randrange(int(lo), int(hi)) // 10 * 10


def _maybe(rng: random.Random, p: float, lo: float, hi: float) -> int:
    return _won(rng, lo, hi) if rng.random() < p else 0


def _fmt(n: int) -> str:
    return f"-{-n:,}" if n < 0 else f"{n:,}"


def sample_return(rng: random.Random) -> dict[str, str]:
    """필드 id → 인쇄 문자열. 0인 칸은 비워 두고, 합계 칸은 0이어도 적는다."""
    term, final = rng.choice((1, 2)), rng.random() < 0.8
    year = rng.choice((2025, 2026))
    start, end = (1, 6) if term == 1 else (7, 12)
    if not final:
        end = 3 if term == 1 else 9
    end_day = 30 if end in (6, 9) else 31

    r = {}  # 줄 번호 → (금액, 세액)
    r[1] = (a := _maybe(rng, 0.6, 1e6, 2e8), a // 10)
    r[2] = (a := _maybe(rng, 0.03, 1e5, 5e6), a // 10)
    r[3] = (a := _maybe(rng, 0.85, 5e6, 3e8), a // 10)
    r[4] = (a := _maybe(rng, 0.4, 1e5, 3e7), a // 10)
    r[5] = (_maybe(rng, 0.05, 1e6, 5e7), 0)
    r[6] = (_maybe(rng, 0.05, 1e5, 1e7), 0)
    r[7] = (a := _maybe(rng, 0.05, 1e5, 5e6), a // 10)
    r[8] = (0, _maybe(rng, 0.03, 1e4, 5e5) * rng.choice((1, -1)))
    r[9] = (sum(r[i][0] for i in range(1, 8)), sum(r[i][1] for i in range(1, 9)))

    r[10] = (a := _won(rng, 1e6, 1.5e8), a // 10)
    r[11] = (0, _maybe(rng, 0.02, 1e5, 2e6))
    r[12] = (a := _maybe(rng, 0.3, 1e6, 3e7), a // 10)
    r[13] = (a := _maybe(rng, 0.05, 1e5, 5e6), a // 10)
    r[14] = (a := _maybe(rng, 0.02, 1e5, 2e6), a // 10)
    r[15] = (a := _maybe(rng, 0.7, 1e5, 4e7), a // 10)
    r[16] = (r[10][0] + sum(r[i][0] for i in range(12, 16)),
             r[10][1] - r[11][1] + sum(r[i][1] for i in range(12, 16)))
    r[17] = (a := _maybe(rng, 0.3, 1e5, 1e7), a // 10)
    r[18] = (r[16][0] - r[17][0], r[16][1] - r[17][1])
    da = r[9][1] - r[18][1]

    r[19] = (0, _maybe(rng, 0.05, 1e4, 2e5))
    gross_card = r[3][0] + r[3][1]
    r[20] = (gross_card, min(gross_card * 13 // 1000, 5_000_000)) if gross_card and rng.random() < 0.7 else (0, 0)
    r[21] = (0, r[19][1] + r[20][1])
    for i in range(22, 29):
        r[i] = (0, _maybe(rng, 0.03, 1e4, 1e6))
    r[29] = (0, _maybe(rng, 0.05, 1e4, 5e5))
    r30 = da - r[21][1] - sum(r[i][1] for i in range(22, 29)) + r[29][1]

    values: dict[str, str] = {}
    for row, (amount, tax) in r.items():
        always = row in (9, 16, 18)
        if amount or (always and row != 8):
            values[f"r{row}.amount"] = _fmt(amount)
        if tax or always:
            values[f"r{row}.tax"] = _fmt(tax)
    values["rda.tax"] = _fmt(da)
    values["r30.tax"] = _fmt(r30)

    region, districts = rng.choice(REGIONS)
    biz_type, item = rng.choice(BIZ_TYPES)
    owner = rng.choice(SURNAMES) + "".join(rng.choices(GIVEN, k=2))
    filed_year, filed_month = (year, end + 1) if end < 12 else (year + 1, 1)
    header = {
        "report.final" if final else "report.prelim": "V",
        "period.year": str(year), "period.term": str(term),
        "period.from_month": str(start), "period.from_day": "1",
        "period.to_month": str(end), "period.to_day": str(end_day),
        "biz.name": f"{rng.choice(NAME_HEAD)} {rng.choice(NAME_TAIL)}", "biz.owner": owner,
        "biz.reg_no": f"{rng.randrange(100, 1000)}-{rng.randrange(10, 100)}-{rng.randrange(10000, 100000)}",
        "biz.address": f"{region} {rng.choice(districts)} {rng.choice(ROADS)} {rng.randrange(1, 300)}",
        "base31.type": biz_type, "base31.item": item, "base31.code": f"{rng.randrange(100000, 1000000)}",
        "base31.amount": _fmt(r[9][0]), "base35.amount": _fmt(r[9][0]),
        "filed.year": str(filed_year), "filed.month": str(filed_month), "filed.day": str(rng.randrange(1, 26)),
        "filed.signer": owner,
    }
    # 실제 서류처럼 머리 칸 일부가 비어 있는 경우도 섞는다.
    for key in list(header):
        if key.startswith(("biz.address", "base31", "filed")) and rng.random() < 0.1:
            header.pop(key)
    return {**header, **values}
