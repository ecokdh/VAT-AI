from types import SimpleNamespace
import pytest
from app.receipts.questions import questions,canonical_answers,validated_answers,facts,incomplete

FOOD={'items':[{'name':'아메리카노','row_type':'item'}]}
PROFILE=SimpleNamespace(has_employees=True,onboarding_completed=True)

def test_client_context_is_required_without_tax_verdict():
    answer={'food':'client'}
    assert [q['id'] for q in questions(FOOD,answer)]==['food','client_context']
    assert incomplete(FOOD,answer,PROFILE)
    for context in ['business_meeting','hospitality']:
        answer={'food':'client','client_context':context}
        assert incomplete(FOOD,answer,PROFILE)==[]
        assert facts(answer)[0] is True  # Declared business relationship, not deductibility.

def test_owner_meal_context_and_stale_followup_pruning():
    assert [q['id'] for q in questions(FOOD,{'food':'owner_meal'})]==['food','owner_context']
    assert facts({'food':'owner_meal'})[0] is None
    assert facts({'food':'owner_meal','owner_context':'business'})[0] is True
    assert facts({'food':'owner_meal','owner_context':'personal'})[0] is False
    assert canonical_answers(FOOD,{'food':'personal','owner_context':'business','client_context':'hospitality'})=={'food':'personal'}
    assert len(questions(FOOD,{'food':'work_meal','meal_people':'both'}))==3

def test_client_other_requires_explanation():
    answer={'food':'client','client_context':'other','detail':'고객에게 행사 다과 제공'}
    assert validated_answers(FOOD,answer)==answer
    assert incomplete(FOOD,answer,PROFILE)==[]
    assert '행사 다과' in facts(answer)[1]
    assert facts(answer)[0] is None
    assert incomplete(FOOD,{'food':'client','client_context':'other'},PROFILE)

def test_mixed_item_purposes_are_saved_but_analysis_stays_pending():
    doc={'items':[{'name':'아메리카노','row_type':'item'},{'name':'세제','row_type':'item'},{'name':'쿠폰','row_type':'discount'}]}
    answer={'use':'mixed','item_use_0':'personal','item_use_1':'business'}
    assert validated_answers(doc,answer)==answer
    assert [q['id'] for q in questions(doc,answer)]==['use','item_use_0','item_use_1']
    assert facts(answer)[0] is None
    assert any('공제 범위' in reason for reason in incomplete(doc,answer,PROFILE))
    assert canonical_answers(doc,{'use':'personal','item_use_0':'business'})=={'use':'personal'}
    with pytest.raises(Exception):validated_answers(doc,{'use':'mixed','item_use_2':'business'})

def test_merchant_name_does_not_set_purpose_or_question_type():
    doc={'fields':{'vendor':'직원식당 주유소'},'items':[]}
    assert [q['id'] for q in questions(doc,{})]==['use']
    assert canonical_answers(doc,{})=={}

def test_http_answer_roundtrip_invalidation_and_noop_save(client):
    import json
    from datetime import date
    from app.main import app
    from app.core.database import get_session
    from app.core.security import create_access_token
    from app.auth.models import User
    from app.receipts.models import Receipt
    from app.transactions.models import Transaction
    from app.receipts.questions import VERSION
    gen=app.dependency_overrides[get_session]();db=next(gen)
    try:
        user=User(email='purpose-v3@example.com',name='테스트',password_hash='unused');db.add(user);db.flush()
        r=Receipt(user_id=user.id,image_url='fixture.png',status='done',ocr_raw=json.dumps({'document':FOOD}));db.add(r);db.flush()
        t=Transaction(user_id=user.id,receipt_id=r.id,direction='purchase',transaction_date=date(2026,10,15),vendor='카페',total_amount=5000,review_status='analyzed',deductible_vat=100,legal_references_json='[{"title":"이전 분석"}]');db.add(t);db.commit();db.refresh(t)
        headers={'Authorization':'Bearer '+create_access_token(user.id,user.email)}
        answer={'food':'client','client_context':'hospitality'}
        saved=client.put(f'/v2/transactions/{t.id}/question-answers',headers=headers,json=answer)
        assert saved.status_code==200,saved.text
        result=saved.json();assert result['review_status']=='stale' and result['deductible_vat']==0 and result['legal_references_json']=='[]'
        assert result['question_rule_version']==VERSION
        assert client.get(f'/v2/transactions/{t.id}/questions',headers=headers).json()['answers']==answer
        assert client.put(f'/v2/transactions/{t.id}/question-answers',headers=headers,json=answer).json()['revision']==result['revision']
        unknown=client.put(f'/v2/transactions/{t.id}/question-answers',headers=headers,json={})
        assert unknown.status_code==200 and unknown.json()['business_related'] is None
    finally:
        gen.close()
