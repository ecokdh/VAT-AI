"""Conservative subtotal selection. No truth values or case IDs are inputs."""
import re,unicodedata

DEFAULT_CONFIG={
 'accepted_labels':['소계','소계금액','상품소계','상품소계금액','중간합계','할인전금액','할인전상품금액','subtotal'],
 'wrong_role_labels':['합계','합계금액','총액','총구매액','결제금액','결제액','받을금액','받은금액','청구금액','조제금액','판매금액'],
}
def canonical(label):
 return re.sub(r'[\s:：()（）]','',unicodedata.normalize('NFKC',str(label or '')).casefold())
def select_subtotal(amount_candidates,ocr_text,config):
 allowed={canonical(x) for x in config['accepted_labels']};wrong={canonical(x) for x in config['wrong_role_labels']}
 evidence=canonical(ocr_text);accepted=[];rejected=[];pending=[]
 for index,c in enumerate(amount_candidates):
  if c.get('role')!='subtotal':continue
  candidate=dict(c,source_index=index);label=canonical(c.get('label'))
  if label in wrong:candidate['decision']='wrong_amount_role';rejected.append(candidate)
  elif label not in allowed:candidate['decision']='unverified_subtotal_label';pending.append(candidate)
  elif not evidence or label not in evidence:candidate['decision']='subtotal_label_not_in_saved_ocr';pending.append(candidate)
  elif c.get('value') is None:candidate['decision']='missing_printed_value';pending.append(candidate)
  else:candidate['decision']='explicit_subtotal_label_candidate';accepted.append(candidate)
 values={x['value'] for x in accepted}
 if len(values)==1:
  value=next(iter(values));status='kept_explicit_subtotal_candidate'
 elif len(values)>1:value=None;status='withheld_conflicting_subtotal_candidates'
 else:value=None;status='withheld_no_supported_subtotal_candidate'
 return {'value':value,'status':status,'accepted_candidates':accepted,'rejected_candidates':rejected,'pending_candidates':pending,'note':'null는 인쇄 없음 확정이 아닌 소계 채택 보류. OCR 라벨 문자열 확인은 역할·값의 사진 근거 검증 전체를 대체하지 않음.'}
