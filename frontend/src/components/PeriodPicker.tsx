import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { periodLabel, periodOptions } from "../hooks/reviewState";

function Wheel({label, options, value, onChange}: {label: string; options: {value: string; label: string}[]; value: string; onChange: (value: string) => void}) {
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  const index = Math.max(0, options.findIndex(o => o.value === value));
  const initialIndex = useRef(index);
  useLayoutEffect(() => {if(ref.current) ref.current.scrollTop = initialIndex.current * 48;}, []); // Scrolling owns subsequent selection.
  function select(next: number) {
    const bounded = Math.max(0, Math.min(options.length - 1, next));
    onChange(options[bounded].value);
    ref.current?.scrollTo({top: bounded * 48, behavior: "instant"});
  }
  return <div className="period-wheel-column"><span className="form-field__label">{label}</span><div className="period-wheel-frame"><div
    ref={ref} className="period-wheel" role="listbox" aria-label={label} tabIndex={0} aria-activedescendant={`${id}-${index}`}
    onScroll={e => {const next = Math.max(0, Math.min(options.length - 1, Math.round(e.currentTarget.scrollTop / 48)));onChange(options[next].value);}}
    onKeyDown={e => {if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {e.preventDefault();select(e.key === "Home" ? 0 : e.key === "End" ? options.length - 1 : index + (e.key === "ArrowDown" ? 1 : -1));}}}>
    {options.map((o, i) => <div id={`${id}-${i}`} key={o.value} role="option" aria-selected={value===o.value} className="period-wheel-option" onClick={()=>select(i)}>{o.label}</div>)}
  </div></div></div>;
}

function PickerDialog({value, simplified, allowAll, onClose, onChange}: {value: string; simplified: boolean; allowAll: boolean; onClose:()=>void; onChange:(value:string)=>void}) {
  const options = periodOptions(simplified);
  const initial = options.includes(value) ? value : options[0];
  const [year, setYear] = useState(initial.slice(0,4));
  const [part, setPart] = useState(initial.slice(5));
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(()=>{dialog.current?.showModal();},[]);
  const years = [...new Set(options.map(p=>p.slice(0,4)))].map(y=>({value:y,label:`${y}년`}));
  const parts = [...new Set(options.map(p=>p.slice(5)))].map(p=>({value:p,label:periodLabel(`${year}-${p}`).slice(6)}));
  function confirm(period: string) {onChange(period);onClose();}
  return <dialog ref={dialog} className="period-dialog" aria-labelledby={titleId} onCancel={e=>{e.preventDefault();onClose();}}>
    <div className="section-heading"><h2 id={titleId}>신고 대상 기간</h2><button type="button" className="icon-btn" aria-label="기간 선택 닫기" onClick={onClose}>×</button></div>
    <p className="muted">연도와 기간을 위아래로 움직여 선택하세요.</p>
    <div className="period-wheels"><Wheel label="연도" options={years} value={year} onChange={setYear}/><Wheel label="신고기간" options={parts} value={part} onChange={setPart}/></div>
    <p className="period-selection" role="status">{periodLabel(`${year}-${part}`)}</p>
    <div className="btn-row"><button type="button" className="btn btn--secondary" onClick={onClose}>취소</button><button type="button" className="btn btn--primary" onClick={()=>confirm(`${year}-${part}`)}>선택 완료</button></div>
    {allowAll && <button type="button" className="text-link period-all" onClick={()=>confirm("all")}>전체 기간 보기</button>}
  </dialog>;
}

export function PeriodPicker({value, simplified=false, allowAll=false, onChange}: {value:string; simplified?:boolean; allowAll?:boolean; onChange:(value:string)=>void}) {
  const [open,setOpen]=useState(false);
  return <div className="form-field period-picker"><span className="form-field__label">신고 대상 기간</span><button type="button" className="input period-trigger" aria-haspopup="dialog" onClick={()=>setOpen(true)}><span>{value==="all"?"전체 기간":periodLabel(value)}</span><span aria-hidden="true">⌄</span></button>{open && <PickerDialog value={value} simplified={simplified} allowAll={allowAll} onClose={()=>setOpen(false)} onChange={onChange}/>}</div>;
}
