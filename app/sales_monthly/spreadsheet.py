"""Read supported Hometax sales spreadsheet layouts."""

from calendar import monthrange
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

from openpyxl import load_workbook
import xlrd

from app.common.exceptions import AppException
from app.receipts.ocr.luna_client import LunaFailure, validate
from app.sales_monthly import service

VERSION = "hometax-spreadsheet-v1"
MIME = {"xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
CARD = ["순번", "승인년월", "자료구분", "건수", "매출액계", "신용카드 결제", "구매전용카드결제", "비과세금액"]
CASH = ["거래년월", "거래건수", "총금액", "공급가액", "세액", "봉사료"]
PG = ["순번", "승인년월", "건수", "매출금액", "판매(결제)대행업체 상호"]
PG_PAYMENTS = {"카드", "증빙 미발급 기타 결제"}
INVOICE = ["작성일자", "승인번호", "발급일자", "전송일자", "공급자사업자등록번호",
           "공급받는자사업자등록번호", "합계금액", "공급가액", "세액", "전자세금계산서분류", "전자세금계산서종류"]
EXTRA_FIELDS = {
    "순번": "integer", "구매전용카드금액": "integer", "발급수단": "string", "발급결과": "string",
    "공급자사업자번호": "string", "전자세금계산서분류": "string", "발급유형": "string",
}
MAX_ROWS = 5000
MAX_COLUMNS = 50


def invalid(message):
    return AppException(400, "INVALID_SALES_SPREADSHEET", message)


def sheet_rows(data, extension, sheet_name=None):
    if extension == "xls":
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        try:
            sheet = book.sheet_by_name(sheet_name) if sheet_name in book.sheet_names() else book.sheet_by_index(0)
            if sheet.nrows > MAX_ROWS or sheet.ncols > MAX_COLUMNS:
                raise invalid("5,000행 이하의 매출 파일을 선택해 주세요.")
            return [tuple(
                xlrd.xldate_as_datetime(cell.value, book.datemode) if cell.ctype == xlrd.XL_CELL_DATE else cell.value
                for cell in sheet.row(index)
            ) for index in range(sheet.nrows)]
        finally:
            book.release_resources()
    with ZipFile(BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 30_000_000:
            raise invalid("엑셀 파일의 내부 데이터가 너무 큽니다.")
    book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
    try:
        sheet = book[sheet_name] if sheet_name in book.sheetnames else book.worksheets[0]
        if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
            raise invalid("5,000행 이하의 매출 파일을 선택해 주세요.")
        rows = []
        for cells in sheet.iter_rows(max_row=sheet.max_row or MAX_ROWS + 1, max_col=sheet.max_column or MAX_COLUMNS):
            if any(cell.data_type == "f" for cell in cells):
                raise invalid("수식이 있는 파일은 가져올 수 없습니다. 홈택스에서 받은 원본을 선택해 주세요.")
            rows.append(tuple(cell.value for cell in cells))
        if len(rows) > MAX_ROWS and any(value is not None for value in rows[-1]):
            raise invalid("5,000행 이하의 매출 파일을 선택해 주세요.")
        return rows[:MAX_ROWS]
    finally:
        book.close()


def text(value):
    return "" if value is None else str(value).strip()


def amount(value, *, optional=False):
    if not text(value) and optional:
        return None
    if isinstance(value, bool):
        raise ValueError("not an amount")
    if isinstance(value, (int, float)) and int(value) == value:
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)", value.strip()):
        return int(value.replace(",", ""))
    raise ValueError("not an amount")


def empty_object(schema):
    return {name: None for name in schema["properties"]}


def normalize_card(rows):
    columns = CARD
    compact = lambda value: re.sub(r"\s+", "", text(value))
    header = next((i for i, row in enumerate(rows[:30])
                   if list(map(compact, row[:len(columns)])) == list(map(compact, columns))), None)
    if header is None:
        raise invalid("승인년월이 있는 카드 월별 표를 올려 주세요. 승인분기 요약 파일은 이 입력에서 사용할 수 없습니다.")
    base = service.LEGACY_SCHEMA["properties"]
    row_schema = service.SCHEMA["properties"]["매출증빙"]["properties"]["내역"]["items"]
    evidence = []
    totals = []
    for sheet_line, raw in enumerate(rows[header + 1:], header + 2):
        if not any(text(value) for value in raw):
            continue
        if len(raw) < len(columns):
            raise invalid(f"엑셀 {sheet_line}행의 열이 부족합니다.")
        row = {**empty_object(row_schema), **dict.fromkeys(EXTRA_FIELDS)}
        try:
            if compact(raw[0]) == "합계":
                totals.append([amount(value, optional=True) for value in raw[3:8]])
                continue
            seq, month, category = amount(raw[0]), text(raw[1]), text(raw[2])
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or not category:
                raise ValueError("card row")
            count, total, card, purchase, exempt = [amount(value, optional=index == 4) for index, value in enumerate(raw[3:8])]
            row.update({"범위": "집계", "순번": seq, "일자또는월": month, "자료구분": category,
                        "원문항목": category, "결제수단": "카드", "건수": count, "합계금액": total,
                        "카드금액": card, "구매전용카드금액": purchase, "비과세금액": exempt})
            if row["합계금액"] == 0 and (row["건수"] == 0 and row["비과세금액"] == 0):
                row["과세구분"] = "과세"
            evidence.append(row)
        except (ValueError, OverflowError):
            raise invalid(f"엑셀 {sheet_line}행의 날짜·구분·금액 형식을 확인해 주세요.") from None
    if not evidence:
        raise invalid("가져올 월별 카드 행이 없습니다.")
    keys = ("건수", "합계금액", "카드금액", "구매전용카드금액", "비과세금액")
    for total in totals:
        if any(value is not None and all(row[key] is not None for row in evidence)
               and sum(row[key] for row in evidence) != value for key, value in zip(keys, total)):
            raise invalid("합계행과 월별 내역의 금액 또는 건수가 다릅니다. 원본을 확인해 주세요.")
    identities = {(row["일자또는월"], row["자료구분"]) for row in evidence}
    if len(identities) != len(evidence):
        raise invalid("같은 승인월·자료구분이 두 번 나옵니다. 중복 행을 확인해 주세요.")
    document = {"사업장": empty_object(base["사업장"]), "거래일": None,
                "집계합계": empty_object(base["집계합계"]), "매출집계_유형별": [],
                "세무조정_필수항목": empty_object(base["세무조정_필수항목"]),
                "매출증빙": {"문서유형": "홈택스카드",
                         "기간시작": None, "기간종료": None, "기준일종류": "승인월",
                         "내역": evidence}}
    return document, []


def normalize_pg(rows):
    def compact(value):
        return re.sub(r"\s+", "", text(value))

    header = next((i for i, row in enumerate(rows[:30])
                   if [compact(value) for value in row if text(value)] == list(map(compact, PG))
                   and list(map(compact, row[:5])) == list(map(compact, PG))), None)
    if header is None:
        raise invalid("판매(결제)대행 표에서 승인년월·건수·매출금액·대행업체 상호가 있는 5열 엑셀을 올려 주세요.")
    row_schema = service.SCHEMA["properties"]["매출증빙"]["properties"]["내역"]["items"]
    evidence, identities = [], set()
    control = None
    for line, raw in enumerate(rows[header + 1:], header + 2):
        if not any(map(text, raw)):
            continue
        try:
            seq, month, count, total, provider = raw[:5]
            if any(map(text, raw[5:])):
                raise ValueError
            count, total = amount(count), amount(total)
            if count < 0:
                raise ValueError
            if compact(seq) == "합계":
                if control is not None or text(month) or text(provider):
                    raise ValueError
                control = (count, total)
                continue
            seq = amount(seq)
            month = month.strftime("%Y-%m") if isinstance(month, (date, datetime)) else text(month)
            provider = text(provider)
            if seq <= 0 or not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", month) or not provider:
                raise ValueError
        except (ValueError, OverflowError):
            raise invalid(f"엑셀 {line}행의 순번·승인년월·건수·매출금액·대행업체 상호를 확인해 주세요.") from None
        identity = (month, compact(provider).casefold())
        if identity in identities:
            raise invalid(f"엑셀 {line}행에 같은 승인월·대행업체가 중복됐습니다.")
        identities.add(identity)
        row = {**empty_object(row_schema), **dict.fromkeys(EXTRA_FIELDS)}
        row.update({"범위": "집계", "순번": seq, "일자또는월": month, "업체명": provider,
                    "원문항목": provider, "건수": count, "합계금액": total})
        evidence.append(row)
    if not evidence:
        raise invalid("가져올 판매·결제대행 월별 행이 없습니다.")
    if control != (sum(row["건수"] for row in evidence), sum(row["합계금액"] for row in evidence)):
        raise invalid("판매·결제대행 합계행의 건수·금액을 월별 내역과 확인해 주세요.")
    base = service.LEGACY_SCHEMA["properties"]
    return {
        "사업장": empty_object(base["사업장"]), "거래일": None,
        "집계합계": empty_object(base["집계합계"]), "매출집계_유형별": [],
        "세무조정_필수항목": empty_object(base["세무조정_필수항목"]),
        "매출증빙": {"문서유형": "홈택스판매결제대행", "기간시작": None, "기간종료": None,
                 "기준일종류": "승인월", "내역": evidence},
    }, ["원본 조회 화면에서 사업자번호와 조회기간을 확인하세요. 카드·기타 금액이 섞인 행은 별도 자료로 대조하세요."]


def normalize_cash_summary(rows):
    row_schema = service.SCHEMA["properties"]["매출증빙"]["properties"]["내역"]["items"]
    evidence, block = [], []
    section = None
    start = end = None
    business_number = business_name = None
    control_rows = []
    in_table = False
    identities = set()

    def validate_totals():
        for label, amounts in control_rows:
            selected = block
            if label.startswith(("상반기", "하반기")):
                selected = [row for row in block if (int(row["일자또는월"][5:]) <= 6) == label.startswith("상반기")]
            for index, key in enumerate(("건수", "합계금액", "공급가액", "부가세", "봉사료")):
                if amounts[index] is not None and all(row[key] is not None for row in selected):
                    if amounts[index] != sum(row[key] for row in selected):
                        raise invalid(f"{section}의 {label}와 월별 {key}가 일치하지 않습니다.")
        control_rows.clear()

    for number, raw in enumerate(rows, 1):
        values = [text(value) for value in raw]
        if not any(values):
            continue
        first = next(value for value in values if value)
        compact = re.sub(r"\s+", "", first)
        if compact.startswith("조회기간"):
            period = re.search(r"(\d{4})[.-](\d{2})\s*[~～]\s*(\d{4})[.-](\d{2})(?![.\d-])", " ".join(values))
            if period:
                try:
                    y1, m1, y2, m2 = map(int, period.groups())
                    start = date(y1, m1, 1).isoformat()
                    end = date(y2, m2, monthrange(y2, m2)[1]).isoformat()
                    if start > end:
                        raise ValueError
                except ValueError:
                    raise invalid("현금영수증 누계의 조회기간을 확인해 주세요.") from None
        for index, value in enumerate(values[:-1]):
            if value in {"사업자번호", "사업자등록번호"} and values[index + 1]:
                business_number = values[index + 1]
            if value == "상호" and values[index + 1]:
                business_name = values[index + 1]
        if "발행내역" in compact and not compact.startswith("조회기간"):
            validate_totals()
            block = []
            section = first
            in_table = False
            continue
        if values[:6] == CASH:
            if not section:
                raise invalid("월별 표 위에 사업자발행내역 등 발행 구역 제목을 포함해 주세요.")
            in_table = True
            continue
        if not in_table:
            continue
        try:
            cells = (*raw[:6], *(None,) * max(0, 6 - len(raw)))
            if "합계" in compact:
                control_rows.append((compact, [amount(value, optional=True) for value in cells[1:]]))
                continue
            month = cells[0].strftime("%Y-%m") if isinstance(cells[0], (date, datetime)) else values[0]
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                raise ValueError
            count, total, supply, vat, fee = [amount(value, optional=index == 4) for index, value in enumerate(cells[1:])]
            if count < 0 or total != supply + vat + (fee or 0):
                raise ValueError
            if start and end and not start[:7] <= month <= end[:7]:
                raise invalid(f"엑셀 {number}행의 거래월이 조회기간 밖입니다.")
            identity = (section, month)
            if identity in identities:
                raise invalid(f"엑셀 {number}행에 같은 발행 구역·거래월이 중복됐습니다.")
            identities.add(identity)
            row = {**empty_object(row_schema), **dict.fromkeys(EXTRA_FIELDS)}
            row.update({"범위": "집계", "원문항목": section, "발행구분": section, "일자또는월": month,
                        "결제수단": "현금영수증", "건수": count, "합계금액": total,
                        "공급가액": supply, "부가세": vat, "봉사료": fee,
                        "과세구분": "과세" if count == total == supply == vat == fee == 0 else None})
            block.append(row)
            evidence.append(row)
        except (ValueError, OverflowError):
            raise invalid(f"엑셀 {number}행의 거래월·건수 또는 총금액(공급가액+세액+봉사료)을 확인해 주세요.") from None
    validate_totals()
    if not evidence:
        raise invalid("거래년월·거래건수·총금액이 있는 현금영수증 매출내역누계 엑셀을 선택해 주세요.")
    base = service.LEGACY_SCHEMA["properties"]
    return {
        "사업장": {"상호": business_name, "사업자등록번호": business_number},
        "거래일": None, "집계합계": empty_object(base["집계합계"]), "매출집계_유형별": [],
        "세무조정_필수항목": empty_object(base["세무조정_필수항목"]),
        "매출증빙": {"문서유형": "홈택스현금영수증", "기간시작": start, "기간종료": end,
                 "기준일종류": "거래년월", "내역": evidence},
    }, ["신고기간 전체와 해당하는 모든 발행 구역이 포함됐는지 원본에서 확인해 주세요."]


def normalize_invoice(rows):
    compact = lambda value: re.sub(r"\s+", "", text(value))
    header = next((i for i, row in enumerate(rows[:30]) if set(INVOICE) <= set(map(compact, row))), None)
    if header is None:
        raise invalid("작성일자·승인번호가 있는 매출 전자세금계산서 목록 엑셀을 올려 주세요. 건별일괄출력은 목록으로 가져올 수 없습니다.")
    positions = {compact(value): index for index, value in enumerate(rows[header])}
    if any(list(map(compact, rows[header])).count(name) != 1 for name in INVOICE):
        raise invalid("전자세금계산서 필수 열 이름이 중복되었습니다.")
    row_schema = service.SCHEMA["properties"]["매출증빙"]["properties"]["내역"]["items"]
    metadata = {}
    for raw in rows[:header]:
        for index, label in enumerate(raw[:-1]):
            if compact(label) in {"사업자등록번호", "상호", "총합계금액", "총공급가액", "총세액"}:
                metadata[compact(label)] = raw[index + 1]
    business_number = re.sub(r"\D", "", text(metadata.get("사업자등록번호")))
    evidence, approvals, supplier_numbers = [], set(), set()

    def read_date(value):
        if isinstance(value, datetime):
            return value.date().isoformat()
        return date.fromisoformat(text(value)).isoformat() if text(value) else None

    for sheet_line, raw in enumerate(rows[header + 1:], header + 2):
        if not any(text(value) for value in raw):
            continue
        def value(name):
            index = positions.get(name)
            return raw[index] if index is not None and index < len(raw) else None
        try:
            written = read_date(value("작성일자"))
            issued = read_date(value("발급일자"))
            sent = read_date(value("전송일자"))
            approval = value("승인번호")
            if not written or not isinstance(approval, str) or not re.fullmatch(r"[0-9A-Za-z-]{12,40}", approval.strip()):
                raise ValueError
            approval = approval.strip()
            key = approval.replace("-", "").lower()
            supplier = re.sub(r"\D", "", text(value("공급자사업자등록번호")))
            buyer = re.sub(r"\D", "", text(value("공급받는자사업자등록번호")))
            if len(supplier) != 10 or len(buyer) != 10:
                raise ValueError
            if key in approvals:
                raise invalid(f"엑셀 {sheet_line}행의 승인번호가 중복되었습니다.")
            approvals.add(key)
            supplier_numbers.add(supplier)
            total, supply, vat = [amount(value(name)) for name in ("합계금액", "공급가액", "세액")]
            if total != supply + vat:
                raise ValueError
            category, kind = text(value("전자세금계산서분류")), text(value("전자세금계산서종류"))
            if not category or not kind:
                raise ValueError
            row = {**empty_object(row_schema), **dict.fromkeys(EXTRA_FIELDS)}
            row.update({"범위": "건별", "원문항목": category, "일자또는월": written, "작성일": written,
                        "발급일": issued, "전송일": sent, "승인번호": approval,
                        "공급자사업자번호": supplier, "공급받는자사업자번호": buyer,
                        "전자세금계산서분류": category, "세금계산서종류": kind, "발급유형": text(value("발급유형")) or None,
                        "합계금액": total, "공급가액": supply, "부가세": vat,
                        "과세구분": "과세" if category in {"세금계산서", "수정세금계산서"} and vat != 0 else None})
            evidence.append(row)
        except (ValueError, OverflowError):
            raise invalid(f"엑셀 {sheet_line}행의 날짜·승인번호·사업자번호·금액 또는 문서 분류를 확인해 주세요.") from None
    if not evidence:
        raise invalid("가져올 매출 전자세금계산서 행이 없습니다.")
    if len(supplier_numbers) != 1 or (business_number and supplier_numbers != {business_number}):
        raise invalid("조회 사업장과 공급자가 일치하지 않습니다. 매출로 조회한 사업장 한 곳의 목록을 올려 주세요.")
    for label, key in (("총합계금액", "합계금액"), ("총공급가액", "공급가액"), ("총세액", "부가세")):
        if metadata.get(label) is not None and amount(metadata[label]) != sum(row[key] for row in evidence):
            raise invalid(f"원본의 {label}과 세금계산서 행 합계가 일치하지 않습니다.")
    base = service.LEGACY_SCHEMA["properties"]
    return {
        "사업장": {"상호": text(metadata.get("상호")) or None, "사업자등록번호": next(iter(supplier_numbers))},
        "거래일": None, "집계합계": empty_object(base["집계합계"]), "매출집계_유형별": [],
        "세무조정_필수항목": empty_object(base["세무조정_필수항목"]),
        "매출증빙": {"문서유형": "매출세금계산서", "기간시작": None, "기간종료": None,
                 "기준일종류": "작성일", "내역": evidence},
    }, ["홈택스 조회 화면에서 반기 전체를 조회했는지 확인하고 조회 시작일·종료일을 입력해 주세요."]


def read(data, filename, source):
    extension = Path(filename).suffix.lower().lstrip(".")
    normalizers = {"card": normalize_card, "cash": normalize_cash_summary, "invoice": normalize_invoice, "pg": normalize_pg}
    if extension not in MIME or source not in normalizers:
        raise invalid("홈택스 매출자료의 XLS·XLSX 파일을 선택해 주세요.")
    try:
        rows = sheet_rows(data, extension, "세금계산서" if source == "invoice" else None)
        document, warnings = normalizers[source](rows)
    except AppException:
        raise
    except Exception:
        raise invalid("엑셀 파일을 읽지 못했습니다. 원본 XLS·XLSX 파일을 확인해 주세요.") from None
    return document, warnings, extension


REVIEW_FIELDS = {
    "홈택스카드": {"순번", "일자또는월", "자료구분", "건수", "합계금액", "카드금액", "구매전용카드금액", "비과세금액"},
    "홈택스현금영수증": {"일자또는월", "발행구분", "건수", "합계금액", "공급가액", "부가세", "봉사료",
                     "승인번호", "발급수단", "용도구분", "거래구분", "발급결과", "원승인번호"},
    "매출세금계산서": {"작성일", "승인번호", "발급일", "전송일", "공급자사업자번호", "공급받는자사업자번호",
                  "합계금액", "공급가액", "부가세", "전자세금계산서분류", "세금계산서종류", "발급유형"},
    "홈택스판매결제대행": {"순번", "일자또는월", "건수", "합계금액", "업체명", "결제수단"},
}


def validate_review(document, original):
    evidence = document["매출증빙"]
    original_evidence = original["매출증빙"]
    kind = original_evidence["문서유형"]
    if (evidence["문서유형"] != kind or evidence["기준일종류"] != original_evidence["기준일종류"]
        or len(evidence["내역"]) != len(original_evidence["내역"])):
        raise LunaFailure("INVALID_SPREADSHEET_REVIEW")
    editable = REVIEW_FIELDS.get(kind, set()) | {"과세구분"}
    cash_summary = kind == "홈택스현금영수증" and evidence["기준일종류"] == "거래년월"
    derived = {"일자또는월", "원문항목"} if kind == "매출세금계산서" else (
        {"원문항목"} if kind in {"홈택스카드", "홈택스판매결제대행"} or cash_summary else set()
    )
    rows = []
    for row, original_row in zip(evidence["내역"], original_evidence["내역"]):
        if any(row.get(name) != value for name, value in original_row.items() if name not in editable | derived):
            raise LunaFailure("INVALID_SPREADSHEET_REVIEW")
        for name, field_type in EXTRA_FIELDS.items():
            if name in original_row:
                validate(row[name], service.optional(field_type))
            elif name in row:
                raise LunaFailure("INVALID_SPREADSHEET_REVIEW")
        rows.append({key: value for key, value in row.items() if key not in EXTRA_FIELDS})
    service.validate_document({**document, "매출증빙": {**evidence, "내역": rows}})

    def reject(message):
        raise AppException(400, "INVALID_REVIEW", message)

    try:
        dates = [date.fromisoformat(evidence[key]) for key in ("기간시작", "기간종료") if evidence[key]]
        if len(dates) == 2 and dates[0] > dates[1]:
            raise ValueError
    except ValueError:
        reject("조회 시작일과 종료일을 확인해 주세요.")

    identities = set()
    for row, original_row in zip(evidence["내역"], original_evidence["내역"]):
        if row == original_row and kind == "홈택스현금영수증" and not cash_summary:
            continue
        label = text(row.get("작성일") or row.get("일자또는월")) or "날짜 미입력"
        try:
            if kind == "매출세금계산서":
                date.fromisoformat(text(row["작성일"]))
                for key in ("발급일", "전송일"):
                    if row[key]:
                        date.fromisoformat(row[key])
                approval = text(row["승인번호"])
                if not re.fullmatch(r"[0-9A-Za-z-]{12,40}", approval):
                    raise ValueError
                identity = approval.replace("-", "").lower()
                for key in ("공급자사업자번호", "공급받는자사업자번호"):
                    row[key] = re.sub(r"[-\s]", "", text(row[key]))
                    if not re.fullmatch(r"[0-9]{10}", row[key]):
                        raise ValueError
                business_number = re.sub(r"[-\s]", "", text(document["사업장"]["사업자등록번호"]))
                if row["공급자사업자번호"] != business_number:
                    reject(f"{label} 세금계산서의 공급자 사업자번호가 문서 상단의 사업자번호와 다릅니다.")
                if not text(row["전자세금계산서분류"]) or not text(row["세금계산서종류"]):
                    raise ValueError
                row["일자또는월"] = row["작성일"]
                row["원문항목"] = row["전자세금계산서분류"]
            elif kind in {"홈택스카드", "홈택스판매결제대행"} or cash_summary:
                if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", label) or row["건수"] is None or row["건수"] < 0:
                    raise ValueError
                group_field = {"홈택스카드": "자료구분", "홈택스판매결제대행": "업체명", "홈택스현금영수증": "발행구분"}[kind]
                group = text(row[group_field])
                if not group or row["합계금액"] is None or ("순번" in editable and (row["순번"] is None or row["순번"] <= 0)):
                    raise ValueError
                identity = (label, re.sub(r"\s+", "", group).casefold())
                row["원문항목"] = group
                if kind == "홈택스판매결제대행" and row["결제수단"] not in PG_PAYMENTS | {None}:
                    raise ValueError
                if kind == "홈택스카드" and (row["카드금액"] is None or row["구매전용카드금액"] is None):
                    raise ValueError
            else:
                identity = None
            if kind == "매출세금계산서" or cash_summary:
                if row["공급가액"] is None or row["부가세"] is None or row["합계금액"] != (
                    row["공급가액"] + row["부가세"] + ((row["봉사료"] or 0) if cash_summary else 0)
                ):
                    reject(f"{label} 자료의 총금액이 공급가액·세액{'·봉사료' if cash_summary else ''}의 합과 다릅니다.")
            if identity is not None:
                if identity in identities:
                    reject(f"{label} 자료에 같은 승인번호 또는 같은 월·구분이 두 번 입력됐습니다.")
                identities.add(identity)
        except ValueError:
            reject(f"{label} 자료의 날짜·구분·번호 또는 금액을 확인해 주세요.")
