import json

from app.deduction.receipt_summary import deduction_summary
from app.receipts.models import Receipt

DOC = {
    'fields': {'vendor': '(주)제이와이에너지', 'business_number': '899-87-03164', 'transaction_datetime': '2023-10-24 20:36:54',
               'supply_amount': 18182, 'vat_amount': 1818, 'payment_amount': 20000, 'discount_amount': None, 'payment_method': '롯데카드'},
    'items': [{'name': '휘발유', 'quantity': 11.635, 'line_amount': 20000, 'row_type': 'item'},
              {'name': '쿠폰', 'line_amount': -1000, 'row_type': 'discount'}],
}


def receipt(raw, details=None):
    return Receipt(user_id='00000000-0000-0000-0000-000000000000', image_url='x.png', status='done',
                   ocr_raw=raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False), details_json=json.dumps(details or {}))


def test_summary_uses_only_deduction_fields():
    raw = {'engine': 'luna_low', 'ocr': {'raw_response': {'images': ['x' * 50000]}}, 'document': DOC}
    assert deduction_summary(receipt(raw)) == (
        '상호: (주)제이와이에너지\n사업자번호: 899-87-03164\n거래일시: 2023-10-24 20:36:54\n결제수단: 롯데카드\n'
        '공급가액: 18182 / 부가세: 1818 / 결제금액: 20000\n품목: 휘발유 x11.635 20000')


def test_summary_prefers_user_review_and_saved_payment_method():
    review = {'fields': {'vendor': '스타벅스', 'branch': '영등포구청역점', 'printed_total_amount': 5400.0, 'payment_amount': 1400.0, 'discount_amount': 4000.0},
              'items': [{'name': '콜드브루', 'quantity': 1.0, 'line_amount': 5400.0, 'row_type': 'item'}]}
    summary = deduction_summary(receipt({'document': DOC, 'review': {'document': review}}, {'payment_method': '스타벅스카드'}))
    assert summary == '상호: 스타벅스 영등포구청역점\n결제수단: 스타벅스카드\n결제금액: 1400 / 할인: 4000\n품목: 콜드브루 x1 5400'


def test_legacy_text_passes_through_and_missing_document_is_none():
    assert deduction_summary(receipt('테스트 상점\n4500')) == '테스트 상점\n4500'
    assert deduction_summary(receipt({'engine': 'luna_low', 'error_code': 'TIMEOUT'})) is None
