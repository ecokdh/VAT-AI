import { useEffect, useState } from "react";
import { getReceiptImage } from "../api/receipts";

export function ReceiptPreview({ id, wide = false, controls = false }: { id: number; wide?: boolean; controls?: boolean }) {
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  const [zoom,setZoom] = useState(1);
  useEffect(() => {
    let active = true;
    let objectUrl = "";
    getReceiptImage(id).then((blob) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id]);
  if(controls)return <figure className="receipt-preview receipt-preview--reference" aria-label="원본 사진">
    <div className="reference-tools"><span>원본 사진</span><div><button type="button" aria-label="사진 축소" disabled={zoom<=1} onClick={()=>setZoom(v=>Math.max(1,v-.5))}>−</button><button type="button" aria-label="사진 확대" disabled={zoom>=3} onClick={()=>setZoom(v=>Math.min(3,v+.5))}>＋</button><button type="button" onClick={()=>setZoom(1)}>맞춤</button></div></div>
    <div className={`reference-image${zoom>1?' reference-image--zoom':''}`} tabIndex={0} aria-label="사진 스크롤 영역">{url?<img src={url} alt="업로드한 증빙 원본" style={{width:`${zoom*100}%`}} />:<span className="muted">{failed?'원본 사진을 불러오지 못했습니다.':'사진을 불러오는 중입니다.'}</span>}</div>
  </figure>;
  return <figure className={`receipt-preview${wide ? " receipt-preview--wide" : ""}`} aria-label="업로드한 증빙 미리보기">
    {url ? <img src={url} alt="업로드한 증빙 원본" /> : <span className="muted">{failed ? "원본 이미지를 불러오지 못했어요" : "원본 이미지를 불러오는 중"}</span>}
    {!wide && <figcaption>업로드한 증빙</figcaption>}
  </figure>;
}
