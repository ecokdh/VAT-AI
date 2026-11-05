"""공제 판단에 넘길 영수증 요약([공제 판단용]). OCR 원본 기록 전체는 넘기지 않는다."""
import json


def _num(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return str(int(value)) if float(value).is_integer() else str(value)


def deduction_summary(receipt) -> str | None:
    try:
        raw = json.loads(receipt.ocr_raw or '{}')
    except ValueError:
        return receipt.ocr_raw  # Luna 이전 방식의 OCR 원문 텍스트
    if not isinstance(raw, dict):
        return None
    original = (raw.get('document') or {}).get('fields') or {}
    document = (raw.get('review') or {}).get('document') or raw.get('document') or {}
    fields = document.get('fields') or {}
    if not fields:
        return None

    amounts = [('공급가액', 'supply_amount'), ('부가세', 'vat_amount'), ('면세금액', 'tax_exempt_amount'), ('결제금액', 'payment_amount')]
    if fields.get('payment_amount') is None:
        amounts.append(('합계', 'printed_total_amount'))
    if fields.get('discount_amount'):
        amounts.append(('할인', 'discount_amount'))
    amount_line = ' / '.join(f'{label}: {_num(fields.get(key))}' for label, key in amounts if _num(fields.get(key)) is not None)

    items = []
    for item in document.get('items') or []:
        if item.get('row_type', 'item') != 'item' or not item.get('name'):
            continue
        quantity, amount = _num(item.get('quantity')), _num(item.get('line_amount'))
        items.append(' '.join(x for x in (item['name'], quantity and f'x{quantity}', amount) if x))

    lines = [
        ('상호', ' '.join(x for x in (fields.get('vendor'), fields.get('branch')) if x)),
        ('사업자번호', fields.get('business_number')),
        ('거래일시', fields.get('transaction_datetime')),
        ('결제수단', receipt.details.get('payment_method') or original.get('payment_method')),
        ('과세유형(영수증 표기)', fields.get('tax_type') or original.get('tax_type')),
    ]
    out = [f'{label}: {value}' for label, value in lines if value]
    if amount_line:
        out.append(amount_line)
    if items:
        out.append('품목: ' + ', '.join(items))
    return '\n'.join(out)
