"""매출 자료 문서 형식(SCHEMA) 검증과 검토용 정규화. 사진 인식은 제공하지 않는다."""
from __future__ import annotations

import copy

from app.receipts.ocr.luna_client import LunaFailure, validate

CONTRACT_VERSION = 'monthly-sales-v2-evidence-1'


def optional(kind):
    return {'type': [kind, 'null']}

def obj(props):
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}

LEGACY_SCHEMA = obj({
    '사업장': obj({'상호': optional('string'), '사업자등록번호': optional('string')}),
    '거래일': optional('string'),
    '집계합계': obj({name: optional('integer') for name in ['총판매액','총할인액','취소환불액','실매출액','과세공급가액','부가세합계','면세매출액']}),
    '매출집계_유형별': {'type':'array', 'items': obj({'원문항목': {'type':'string'}, '결제수단': {'type':['string','null'], 'enum':['카드','현금','간편결제','계좌이체','포인트','기타',None]}, '과세구분': {'type':['string','null'], 'enum':['과세','면세','영세율',None]}, '합계금액': optional('integer'), '공급가액': optional('integer'), '부가세': optional('integer')})},
    '세무조정_필수항목': obj({name: optional('integer') for name in ['할인액','취소환불액','포인트사용액','현금영수증발행액']})
})

EVIDENCE_TYPES = [
    'POS정산', '홈택스카드', '홈택스현금영수증', '매출세금계산서', '매출계산서',
    '홈택스판매결제대행', '플랫폼정산', '기타매출장', '확인필요',
]
SCHEMA = obj({
    **LEGACY_SCHEMA['properties'],
    '매출증빙': obj({
        '문서유형': {'type': 'string', 'enum': EVIDENCE_TYPES},
        '기간시작': optional('string'),
        '기간종료': optional('string'),
        '기준일종류': optional('string'),
        '내역': {'type': 'array', 'items': obj({
            '범위': {'type': ['string', 'null'], 'enum': ['건별', '집계', '합계', None]},
            **{name: optional('string') for name in (
                '원문항목', '일자또는월', '결제수단', '자료구분', '거래구분', '발행구분', '용도구분', '과세구분',
                '업체명', '승인번호', '원승인번호', '주문번호', '공급받는자사업자번호',
                '작성일', '발급일', '전송일', '세금계산서종류', '수정사유',
            )},
            **{name: optional('integer') for name in (
                '건수', '합계금액', '공급가액', '부가세', '비과세금액', '봉사료',
                '카드금액', '기타결제금액', '취소환불액', '수수료', '실입금액',
            )},
        })},
    }),
})


def validate_document(document: dict, *, legacy_allowed: bool = False) -> None:
    if legacy_allowed and '매출증빙' not in document:
        validate(document, LEGACY_SCHEMA)
        return
    validate(document, SCHEMA)
    if document['매출증빙']['문서유형'] != 'POS정산' and document['매출집계_유형별']:
        raise LunaFailure('EVIDENCE_IN_POS_LINES')

def prepare_review(raw: dict) -> dict:
    normalized = copy.deepcopy(raw)
    conversions = []
    for section, fields in [('집계합계',['총할인액','취소환불액']), ('세무조정_필수항목',['할인액','취소환불액'])]:
        for name in fields:
            value = normalized[section][name]
            if isinstance(value, int) and not isinstance(value, bool) and value < 0:
                normalized[section][name] = abs(value)
                conversions.append({'field': section+'.'+name, 'raw': value, 'normalized': abs(value)})
    totals = normalized['집계합계']
    gross, discount, refund, net = [totals[k] for k in ('총판매액','총할인액','취소환불액','실매출액')]
    warnings = []
    if all(v is not None for v in (gross, discount, refund, net)) and gross-discount-refund != net:
        warnings.append('총판매액에서 할인과 환불을 뺀 값이 실매출액과 다릅니다.')
    return {'raw_prediction': raw, 'document': normalized, 'conversions': conversions, 'warnings': warnings}

