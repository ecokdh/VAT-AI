// Development-only visual fixture. Not a production entry, no network adapter calls.
import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {apiClient} from '../src/api/client';
import {AmountVisibilityProvider} from '../src/context/AmountVisibilityContext';
import {emptyTaxProfile} from '../src/components/TaxProfileFields';
import {inPeriod, needsReview} from '../src/hooks/reviewState';
import '../src/styles/tokens.css';
import '../src/styles/global.css';
import '../src/styles/ui.css';
import App from '../src/App';
import '../src/styles/qa-polish.css';

if (!import.meta.env.DEV) throw Error('Development fixture only');
const user={id:'mobile-qa-fixture',email:'mobile-qa@example.com',name:'가상대표',nickname:'별빛사장',ocr_guide_seen:true,created_at:'2026-10-19',business:{business_name:'별빛 상점',business_number:'0000000000',tax_type:'일반과세',tax_type_code:'01'}};
const profile={...emptyTaxProfile,entity_type:'individual',industry_category:'other',business_start_date:'2025-01-01',taxable_sales_h1:0,taxable_sales_h2:0,confirmed:false,confirmed_at:null};
const receipt={id:901,user_id:user.id,direction:'purchase',status:'done',vendor:'모바일 검토용 가상 문구점',amount:11000,date:'2026-10-19',details:{},extraction_confirmed:false,
  recognition:{engine:'fixture',document:{fields:{vendor:'모바일 검토용 가상 문구점',business_number:'000-00-00000',payment_amount:11000,supply_amount:10000,vat_amount:1000,transaction_datetime:'2026-10-19 12:30'},items:[{name:'업무용 복사용지 A4',raw_name:'업무용 복사용지 A4',source_row:0,quantity:1,unit_price:11000,line_amount:11000,row_type:'item',parent_row:null}],conflicts:[],uncertain:[]}}};
const rows=[['purchase','confirmed','analyzed','공제 완료 거래'],['purchase','confirmed','excluded','불공제 거래'],['purchase','confirmed','caution','추가 확인할 거래'],['sales','draft','not_analyzed','미확정 매출'],['purchase','confirmed','pending','공제 분석 대기']].map(([direction,state,review_status,description],i)=>({id:i+1,direction,state,review_status,description,vendor:description,transaction_date:'2026-10-19',total_amount:11000,supply_amount:10000,vat_amount:1000,receipt_id:901,deleted_at:null,legal_references_json:'[]'}));
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="320" height="430"><rect width="320" height="430" fill="#fffdf8"/><g fill="#142039" font-family="sans-serif" text-anchor="middle"><text x="160" y="50" font-size="22">가상 영수증</text><text x="160" y="85" font-size="14">모바일 화면 검토 전용</text><path d="M25 110h270M25 280h270" stroke="#888" stroke-dasharray="4 4"/><text x="160" y="155" font-size="16">업무용 복사용지 A4</text><text x="160" y="200" font-size="16">1 × 11,000</text><text x="160" y="325" font-size="24">합계 11,000원</text><text x="160" y="385" font-size="13">실제 거래가 아닙니다</text></g></svg>';
apiClient.defaults.adapter=async config=>{
  const url=config.url??''; const body=typeof config.data==='string'?JSON.parse(config.data):config.data;
  let data:unknown;
  if(url==='/auth/me') {if(config.method==='patch')user.nickname=body.nickname;data=user;}
  else if(url==='/v2/business/profile')data={...user.business,declared_tax_type:'general',entity_type:'individual',operating_industry:'other',business_description:'가상 소매점',has_employees:false,onboarding_completed:true};
  else if(url==='/v2/business/tax-profile')data=profile;
  else if(url==='/v2/transactions')data=rows.filter(r=>r.direction===config.params.direction);
  else if(url==='/v2/receipt-inbox')data=[receipt];
  else if(url.includes('filing-readiness')) {const period=config.params.period;const current=rows.filter(r=>inPeriod(r.transaction_date,period));const inbox=inPeriod(receipt.date,period)?1:0;data={period,total:current.length+inbox,unconfirmed:current.filter(r=>r.state!=='confirmed').length+inbox,pending:current.filter(r=>r.state==='confirmed'&&needsReview(r as never)).length,deductible:current.filter(r=>r.review_status==='analyzed').length,nondeductible:current.filter(r=>r.review_status==='excluded').length};}
  else if(url.includes('tax-estimates'))data={period:config.params.period,status:'PARTIAL',eligible_input_vat:1000,deemed_input_vat:0,payable_estimate:9000,notes:[]};
  else if(url.endsWith('/image'))data=new Blob([svg],{type:'image/svg+xml'});
  else if(url.endsWith('/questions'))data={questions:[{id:'goods',label:'구입한 물품·서비스는 어디에 사용했나요?',options:[{value:'business',label:'실제 업무·매장 운영에 사용'},{value:'personal',label:'개인 용도로 사용'}]}],answers:body??{},profile_complete:true};
  else if(/\/receipts\/901$/.test(url))data=receipt;
  else if(url==='/auth/email-availability')data={available:true};
  else throw Error(`Unconfigured fixture: ${config.method} ${url}`);
  return {config,data,status:200,statusText:'OK',headers:{}};
};
const route=new URLSearchParams(location.search).get('screen')??'/receipts/901/review';
createRoot(document.getElementById('root')!).render(<><div style={{padding:'8px',background:'#fff1db',color:'#80500f',fontSize:12,textAlign:'center'}}>모바일 QA · 가상 데이터 · 서버 저장 없음</div><MemoryRouter initialEntries={[route]}><AmountVisibilityProvider><App/></AmountVisibilityProvider></MemoryRouter></>);
