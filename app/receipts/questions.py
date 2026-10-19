"""Versioned user-fact questions. These rules do not decide tax eligibility."""
import json
import re
from app.common.exceptions import AppException

VERSION = 'purchase-purpose-v3'
OPTIONS = {
    'use': [('business','실제 업무·매장 운영에 사용'),('personal','개인·가족 생활에 사용'),('mixed','업무와 개인 용도가 섞임'),('other','기타 — 직접 입력'),('unknown','아직 확인하지 못함')],
    'food': [('work_meal','사업주·직원 식사·간식'),('client','거래처·고객에게 제공한 식사·음식'),('ingredients','판매할 음식·조리 재료'),('owner_meal','사업주 본인이 먹은 식사'),('personal','개인·가족 식사'),('mixed','여러 목적이 섞임'),('other','기타 — 직접 입력'),('unknown','아직 확인하지 못함')],
    'meal_people': [('owner','사업주 본인'),('employees','직원'),('both','사업주와 직원'),('unknown','아직 확인하지 못함')],
    'goods': [('resale','다시 판매할 상품'),('operations','업무·매장 운영에 사용할 물품'),('personal','개인·가족이 사용할 물품'),('mixed','여러 용도가 섞임'),('other','기타 — 직접 입력'),('unknown','아직 확인하지 못함')],
    'vehicle': [('business','업무를 위한 이동·운행'),('personal','개인·가족의 이동·운행'),('mixed','업무와 개인 운행이 섞임'),('other','기타 — 직접 입력'),('unknown','아직 확인하지 못함')],
    'owner_context': [('business','업무 중 식사'),('personal','개인적인 식사'),('unknown','아직 확인하지 못함')],
    'client_context': [('business_meeting','업무 협의를 위한 식사'),('hospitality','관계 유지·접대를 위한 식사'),('other','기타 — 직접 입력'),('unknown','아직 확인하지 못함')],
    'item_use': [('business','업무·사업에 사용'),('personal','개인·가족이 사용'),('mixed','이 품목도 여러 목적이 섞임'),('unknown','아직 확인하지 못함')],
}
TITLES={'use':'구입한 물품·서비스는 어디에 사용했나요?','food':'이 음식은 어떤 목적으로 구매했나요?','meal_people':'누가 식사했나요?','goods':'구입한 물품은 어디에 사용할 예정인가요?','vehicle':'어떤 이동·운행에 사용한 비용인가요?','owner_context':'사업주 식사는 어떤 상황이었나요?','client_context':'거래처·고객과의 식사는 어떤 상황이었나요?'}


def get_item_key(item: dict, default_index: int) -> str:
    """Stable item identifier across deletions/additions/re-queries."""
    if item.get('item_id'):
        return str(item['item_id'])
    # If source_row is present (OCR model original row index), use it for stable tracking
    if item.get('source_row') is not None:
        return f"src_{item['source_row']}"
    return str(default_index)


def get_item_by_key(document: dict, item_key: str) -> tuple[int, dict] | None:
    items = [i for i in document.get('items', []) if i.get('row_type', 'item') == 'item']
    for idx, item in enumerate(items):
        if get_item_key(item, idx) == item_key:
            return idx, item
        # also match legacy row index if no explicit source_row
        if item_key.isdecimal() and int(item_key) == idx and item.get('source_row') is None:
            return idx, item
        if item_key.isdecimal() and item.get('source_row') == int(item_key):
            return idx, item
    return None


def active_keys(document, answers):
    root = category(document)
    root = 'use' if root == 'generic' else root
    keys = [root]
    if root == 'food':
        if answers.get(root) == 'work_meal':
            keys.append('meal_people')
            if answers.get('meal_people') in ('owner', 'both'):
                keys.append('owner_context')
        if answers.get(root) == 'owner_meal':
            keys.append('owner_context')
        if answers.get(root) == 'client':
            keys.append('client_context')
    if answers.get(root) == 'mixed':
        items = [i for i in document.get('items', []) if i.get('row_type', 'item') == 'item']
        for idx, item in enumerate(items):
            ikey = get_item_key(item, idx)
            keys.append(f'item_use_{ikey}')
    if any(answers.get(key) == 'other' for key in keys):
        keys.append('detail')
    return keys


def category(document):
    # Prefer item evidence. A merchant name alone never establishes purpose.
    names = ' '.join(str(i.get('name', '')) for i in document.get('items', []) if i.get('row_type', 'item') == 'item').lower()
    hits = []
    if any(k in names for k in ('휘발유', '경유', '주유', '자동차', '차량')):
        hits.append('vehicle')
    if any(k in names for k in ('커피', '아메리카노', '라떼', '식사', '김밥', '육회', '덮밥', '식재료', '빵', '우유', '치킨', '샐러드', '김치', '양파', '감자', '쌀', '생수', '육류', '돼지', '소고기', '닭', '새우', '토마토', '음료', '국수', '비빔밥', '볶음밥', '초밥', '파스타', '피자', '햄버거', '과자', '소주', '맥주', 'coffee', 'espresso', 'latte', 'milk')):
        hits.append('food')
    if any(k in names for k in ('세제', '휴지', '청소', '문구', '용지', '봉투', '비누', '물품')):
        hits.append('goods')
    return hits[0] if len(hits) == 1 else 'generic'


def canonical_answers(document, answers, direction='purchase'):
    if direction != 'purchase':
        return {}
    answers = {k: v for k, v in (answers or {}).items() if v != ''}
    root = category(document)
    root = 'use' if root == 'generic' else root
    converted = dict(answers)

    # Preserve v1 facts in the v2 form; never mutate the stored old response on read.
    if root == 'food' and converted.get('food') == 'staff':
        converted['food'] = 'work_meal'
        converted.setdefault('meal_people', 'employees')
    if root not in converted and root != 'use' and converted.get('use') in ('personal', 'mixed', 'unknown'):
        converted[root] = converted['use']

    # Migrate legacy row-index item_use_X answers safely to persistent item keys:
    # Only connect if the target item unambiguously exists; if deleted or shifted, do NOT reassign to another item!
    items = [i for i in document.get('items', []) if i.get('row_type', 'item') == 'item']
    active_item_keys = {get_item_key(item, idx) for idx, item in enumerate(items)}

    for k, v in list(converted.items()):
        if k.startswith('item_use_'):
            suffix = k.removeprefix('item_use_')
            if suffix in active_item_keys:
                continue
            # Check if suffix is a decimal legacy index (e.g. item_use_0)
            if suffix.isdecimal():
                old_idx = int(suffix)
                # Find if any item in current document has source_row == old_idx
                matched_item = next((item for item in items if item.get('source_row') == old_idx), None)
                if matched_item is not None:
                    new_key = f"item_use_{get_item_key(matched_item, items.index(matched_item))}"
                    converted[new_key] = v
                elif old_idx < len(items) and items[old_idx].get('source_row') is None:
                    # Legacy unindexed items (e.g. unit tests without source_row)
                    pass
                else:
                    # Item was deleted or ambiguous; leave unmapped (needs re-confirmation)
                    pass

    active = active_keys(document, converted)
    return {k: converted[k] for k in active if k in converted}


def questions(document, answers=None, direction='purchase', profile=None):
    if direction != 'purchase':
        return []
    answers = canonical_answers(document, answers, direction)
    result = []
    items = [i for i in document.get('items', []) if i.get('row_type', 'item') == 'item']
    for key in active_keys(document, answers):
        if key == 'detail':
            continue
        if key.startswith('item_use_'):
            suffix = key.removeprefix('item_use_')
            matched = get_item_by_key(document, suffix)
            if matched:
                idx, item = matched
                label = f"{idx+1}. {item.get('name') or '품목'} — 사용 목적"
            else:
                label = f"품목 {suffix} — 사용 목적"
            options = OPTIONS['item_use']
        else:
            label = TITLES[key]
            options = OPTIONS[key]
        result.append({'id': key, 'label': label, 'options': [{'value': v, 'label': l} for v, l in options]})
    return result


def validated_answers(document, answers, direction='purchase', profile=None):
    items = [i for i in document.get('items', []) if i.get('row_type', 'item') == 'item']
    valid_item_keys = set()
    for idx, item in enumerate(items):
        valid_item_keys.add(f"item_use_{get_item_key(item, idx)}")
        valid_item_keys.add(f"item_use_{idx}")
        if item.get('source_row') is not None:
            valid_item_keys.add(f"item_use_{item['source_row']}")
            valid_item_keys.add(f"item_use_src_{item['source_row']}")

    for k, v in answers.items():
        if not isinstance(v, str) or len(v) > 1000:
            raise AppException(400, 'INVALID_QUESTION_ANSWER', '확인 질문의 답변을 확인해 주세요.')
        if not v:
            continue
        if k == 'detail':
            continue
        if k.startswith('item_use_'):
            if k in valid_item_keys and v in {code for code, _ in OPTIONS['item_use']}:
                continue
            raise AppException(400, 'INVALID_QUESTION_ANSWER', '품목별 사용 목적을 확인해 주세요.')
        if k not in OPTIONS or (v not in {a for a, b in OPTIONS[k]} and not (k == 'food' and v == 'staff')):
            raise AppException(400, 'INVALID_QUESTION_ANSWER', '확인 질문의 답변을 확인해 주세요.')

    result = canonical_answers(document, answers, direction)
    if 'detail' in result:
        result['detail'] = result['detail'].strip()
    return result


def facts(answers):
    # Classification is a user-declared relationship, not a deduction verdict.
    if answers.get('food') == 'staff':
        answers = {**answers, 'food': 'work_meal', 'meal_people': 'employees'}
    root = next((k for k in ('food', 'goods', 'vehicle', 'use') if k in answers), None)
    value = answers.get(root)
    related = True if value in ('business', 'work_meal', 'client', 'ingredients', 'resale', 'operations') else False if value == 'personal' else None
    if value == 'owner_meal' or (value == 'work_meal' and answers.get('meal_people') in ('owner', 'both')):
        context = answers.get('owner_context')
        related = True if context == 'business' else False if context == 'personal' and answers.get('meal_people') != 'both' else None
    if value == 'work_meal' and not answers.get('meal_people'):
        related = None
    if value == 'client' and answers.get('client_context') not in ('business_meeting', 'hospitality'):
        related = None
    parts = [label for k, v in answers.items() for code, label in OPTIONS.get(k, []) if code == v]
    if 'other' in answers.values() and answers.get('detail'):
        parts.append('직접 입력: ' + answers['detail'])
    for key, v in answers.items():
        if key.startswith('item_use_'):
            label = dict(OPTIONS['item_use']).get(v)
            if label:
                suffix = key.removeprefix('item_use_')
                if suffix.startswith('src_'):
                    raw_n = suffix.removeprefix('src_')
                    num_str = str(int(raw_n) + 1) if raw_n.isdecimal() else raw_n
                    parts.append(f"품목 {num_str}: {label}")
                elif suffix.isdecimal():
                    parts.append(f"품목 {int(suffix)+1}: {label}")
                else:
                    parts.append(f"품목 ({suffix}): {label}")
    return related, ' / '.join(parts) or None


def incomplete(document, answers, profile):
    answers = canonical_answers(document, answers)
    reasons = []
    if not profile or not profile.onboarding_completed:
        reasons.append('사업 프로필 확인이 필요합니다.')
    for q in questions(document, answers, profile=profile):
        if answers.get(q['id']) in (None, 'unknown', 'mixed'):
            reasons.append(q['label'])
    if 'other' in answers.values() and not answers.get('detail', '').strip():
        reasons.append('실제 사용 상황을 직접 입력해 주세요.')
    if 'mixed' in answers.values():
        reasons.append('혼합 지출의 품목별 금액과 공제 범위를 추가 확인해야 합니다.')
    if profile and profile.has_employees is False and answers.get('meal_people') in ('employees', 'both'):
        reasons.append('사업 프로필의 직원 유무와 식사한 사람을 함께 확인해 주세요.')
    return reasons


def receipt_document(receipt):
    try:
        raw = json.loads(receipt.ocr_raw or '{}')
        return (raw.get('review') or {}).get('document') or raw.get('document') or {}
    except (ValueError, AttributeError):
        return {}
