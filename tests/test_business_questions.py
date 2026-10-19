import json
from datetime import date
from types import SimpleNamespace
import pytest
from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.core.database import get_session
from app.core.security import create_access_token
from app.main import app
from app.receipts.models import Receipt
from app.receipts.questions import category,questions,validated_answers,VERSION
from app.receipts.schemas import restored_review
from app.transactions.models import Transaction

def setup(client):
    gen=app.dependency_overrides[get_session]();s=next(gen)
    u=User(email='questions@example.com',name='테스트',password_hash='fixture');s.add(u);s.flush()
    b=BusinessProfile(user_id=u.id,business_number='1234567890',business_name='원래 상호',tax_type='조회된 일반과세',verification_status='unverified');s.add(b)
    doc={'fields':{'vendor':'카페','payment_amount':11000,'transaction_datetime':'2026-10-13'},'items':[{'name':'아메리카노','raw_name':'아메리카노','quantity':1,'unit_price':None,'line_amount':11000,'row_type':'item','parent_row':None}],'conflicts':[],'uncertain':[]}
    r=Receipt(user_id=u.id,image_url='fixture.png',status='done',direction='purchase',ocr_raw=json.dumps({'engine':'luna_low','document':doc},ensure_ascii=False));s.add(r);s.commit();s.refresh(r)
    return gen,s,u,r,doc,{'Authorization':'Bearer '+create_access_token(u.id,u.email)}

@pytest.mark.parametrize('name,kind',[('아메리카노','food'),('휘발유','vehicle'),('청소 세제','goods'),('알 수 없는 상품명','generic'),('아메리카노 세제','generic')])
def test_question_category(name,kind):
    assert category({'items':[{'name':name}]})==kind
    assert category({'fields':{'vendor':'주유소 음식점'},'items':[]})=='generic'

def test_dynamic_questions_and_unknowns():
    doc={'items':[{'name':'아메리카노'}]}
    assert [q['id'] for q in questions(doc,{})]==['food']
    assert [q['id'] for q in questions(doc,{'use':'personal'})]==['food']
    assert [q['id'] for q in questions(doc,{'use':'business'})]==['food']
    assert questions(doc,{},direction='sales')==[]
    assert validated_answers(doc,{'use':''})=={}
    q=questions(doc,{'use':'business'},profile=SimpleNamespace(has_employees=False))[-1]
    assert 'work_meal' in [o['value'] for o in q['options']]
    assert [q['id'] for q in questions(doc,{'food':'work_meal'})]==['food','meal_people']


def test_owner_meal_other_and_legacy_answer_compatibility():
    from app.receipts.questions import canonical_answers,incomplete,facts
    doc={'items':[{'name':'아메리카노'}]}
    profile=SimpleNamespace(has_employees=False,onboarding_completed=True)
    owner={'food':'work_meal','meal_people':'owner','owner_context':'business'}
    assert incomplete(doc,owner,profile)==[]
    assert facts(owner)[0] is True
    assert incomplete(doc,{'food':'work_meal','meal_people':'employees'},profile)
    assert canonical_answers(doc,{'use':'business','food':'staff'})=={'food':'work_meal','meal_people':'employees'}
    assert canonical_answers(doc,{'food':'personal','meal_people':'owner'})=={'food':'personal'}
    assert incomplete(doc,{'food':'other'},profile)
    assert incomplete(doc,{'food':'other','detail':'회의에서 제공한 다과'},profile)==[]
    assert facts({'food':'other','detail':'회의에서 제공한 다과'})[0] is None
    assert '회의에서 제공한 다과' in facts({'food':'other','detail':'회의에서 제공한 다과'})[1]
    assert incomplete(doc,{'food':'unknown'},profile)


def test_other_text_is_saved_and_readback_does_not_rewrite_old_answers(client):
    gen,s,u,r,doc,h=setup(client)
    try:
        answers={'food':'other','detail':'회의에 참석한 사람들에게 제공한 다과'}
        body={'vendor':'카페','amount':11000,'date':'2026-10-13','document':{'fields':doc['fields'],'items':[{**doc['items'][0],'source_row':0}]},'question_answers':answers}
        response=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=h,json=body)
        assert response.status_code==200,response.text
        assert response.json()['review']['question_answers']==answers
        assert '회의에 참석한 사람들' in response.json()['review']['purpose']
        assert response.json()['review']['business_related'] is None
        t=Transaction(user_id=u.id,receipt_id=r.id,direction='purchase',transaction_date=date(2026,10,13),vendor='카페',total_amount=11000,question_rule_version='purchase-purpose-v1',question_answers_json=json.dumps({'use':'business','food':'staff'}))
        s.add(t);s.commit();s.refresh(t);before=t.question_answers_json
        read=client.get(f'/v2/transactions/{t.id}/questions',headers=h)
        assert read.json()['answers']=={'food':'work_meal','meal_people':'employees'}
        s.refresh(t);assert t.question_answers_json==before and t.question_rule_version=='purchase-purpose-v1'
    finally:gen.close()

def test_profile_receipt_answers_transaction_roundtrip_and_invalidation(client):
    gen,s,u,r,doc,h=setup(client)
    try:
        assert client.get('/v2/business/profile',headers=h).json()['onboarding_completed'] is False
        profile={'business_name':'원래 상호','declared_tax_type':'general','entity_type':'individual','operating_industry':'cafe','business_description':'카페 운영','has_employees':True}
        saved=client.put('/v2/business/profile',headers=h,json=profile)
        assert saved.status_code==200,saved.text
        assert saved.json()['onboarding_completed'] and saved.json()['verified_tax_type']=='조회된 일반과세'
        q=client.post(f'/v2/receipts/{r.id}/questions',headers=h,json={'use':'business'}).json()
        assert [x['id'] for x in q['questions']]==['food']
        body={'vendor':'카페','amount':11000,'date':'2026-10-13','document':{'fields':doc['fields'],'items':[{**doc['items'][0],'source_row':0}]},'question_answers':{'use':'business','food':'staff'}}
        out=client.post(f'/v2/receipts/{r.id}/confirm-extraction',headers=h,json=body)
        assert out.status_code==200,out.text
        assert out.json()['review']['business_related'] is True
        assert out.json()['review']['question_answers']=={'food':'work_meal','meal_people':'employees'}
        created=client.post(f'/v2/transactions/from-receipt/{r.id}',headers=h,json={'direction':'purchase','transaction_date':'2026-10-13','vendor':'카페','total_amount':11000,'evidence_type':'card_receipt'})
        assert created.status_code==201,created.text
        t=created.json();assert json.loads(t['question_answers_json'])=={'food':'work_meal','meal_people':'employees'} and t['question_rule_version']==VERSION
        changed=client.put(f"/v2/transactions/{t['id']}/question-answers",headers=h,json={'use':'personal'})
        assert changed.status_code==200 and changed.json()['business_related'] is False
        assert changed.json()['review_status']=='stale' and changed.json()['revision']>t['revision']
        before=changed.json()['revision']
        assert client.put('/v2/business/profile',headers=h,json={**profile,'has_employees':False}).status_code==200
        s.expire_all();assert s.get(Transaction,t['id']).revision>before
    finally:gen.close()

def test_missing_facts_skip_analyzer_but_keep_transaction(client,monkeypatch):
    from app.jobs.worker import process_analysis_run
    from app.jobs import worker
    from app.transactions.service import create_analysis_run
    from app.transactions.schemas import AnalysisRunCreate
    gen,s,u,r,doc,h=setup(client)
    try:
        t=Transaction(user_id=u.id,receipt_id=r.id,direction='purchase',transaction_date=date(2026,10,13),vendor='카페',total_amount=11000,state='confirmed',question_rule_version=VERSION)
        s.add(t);s.commit();s.refresh(t)
        run=create_analysis_run(s,u.id,AnalysisRunCreate(transaction_ids=[t.id]))
        class Never:
            def analyze(self,request):raise AssertionError('Missing facts must not reach an external analyzer')
        monkeypatch.setattr(worker,'load_analyzer',lambda _:Never())
        process_analysis_run(s,run);s.commit();s.refresh(t)
        assert t.review_status=='caution' and t.deductible_vat==0
        assert '사업 프로필' in t.analysis_reason and '어떤 목적으로' in t.analysis_reason
    finally:gen.close()

def test_ownership_and_invalid_answers(client):
    gen,s,u,r,doc,h=setup(client)
    try:
        other=User(email='other-questions@example.com',name='다른 사용자',password_hash='fixture');s.add(other);s.commit();s.refresh(other)
        oh={'Authorization':'Bearer '+create_access_token(other.id,other.email)}
        assert client.post(f'/v2/receipts/{r.id}/questions',headers=oh,json={}).status_code==404
        assert client.post(f'/v2/receipts/{r.id}/questions',headers=h,json={}).status_code==200
        with pytest.raises(Exception):validated_answers(doc,{'use':'made-up'})
    finally:gen.close()

def test_old_review_unique_relink_and_ambiguous_reference_stays_unresolved():
    item={'name':'표시 이름','raw_name':'원출력','quantity':1,'unit_price':None,'line_amount':100,'row_type':'item','parent_row':None}
    raw={'document':{'items':[item]},'review':{'document':{'items':[{**item,'name':'수정 이름'}]}}}
    assert restored_review(raw)['document']['items'][0]['source_row']==0
    assert 'source_row' not in raw['review']['document']['items'][0]
    raw['document']['items'].append(dict(item))
    assert 'source_row' not in restored_review(raw)['document']['items'][0]


def test_profile_or_answer_change_during_analysis_cannot_publish_stale_result(client,monkeypatch):
    from app.jobs import worker
    from app.transactions.service import create_analysis_run
    from app.transactions.schemas import AnalysisRunCreate
    from app.analysis.contract import AnalysisDecision
    gen,s,u,r,doc,h=setup(client)
    try:
        p=TaxProfileV2(user_id=u.id,onboarding_completed=True,has_employees=True);s.add(p)
        t=Transaction(user_id=u.id,receipt_id=r.id,direction='purchase',transaction_date=date(2026,10,13),vendor='카페',total_amount=11000,state='confirmed',question_rule_version=VERSION,question_answers_json=json.dumps({'use':'business','food':'staff'}))
        s.add(t);s.commit();s.refresh(t)
        run=create_analysis_run(s,u.id,AnalysisRunCreate(transaction_ids=[t.id]))
        class Changing:
            def analyze(self,request):
                t.revision+=1;t.review_status='stale';s.add(t);s.commit()
                return AnalysisDecision(disposition='NEEDS_REVIEW',reason='outdated result',analyzer_name='fixture',analyzer_version='1')
        monkeypatch.setattr(worker,'load_analyzer',lambda _:Changing())
        worker.process_analysis_run(s,run);s.commit();s.refresh(t)
        assert t.review_status=='stale'
        assert json.loads(run.result_json)[0]['status']=='SKIPPED_STALE'
    finally:gen.close()
