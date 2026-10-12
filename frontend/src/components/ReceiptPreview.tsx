import { useEffect, useState } from "react";
import { getReceiptImage } from "../api/receipts";

export function ReceiptPreview({ id, wide = false }: { id: number; wide?: boolean }) {
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
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
  return <figure className={`receipt-preview${wide ? " receipt-preview--wide" : ""}`} aria-label="업로드한 증빙 미리보기">
    {url ? <img src={url} alt="업로드한 증빙 원본" /> : <span className="muted">{failed ? "원본 이미지를 불러오지 못했어요" : "원본 이미지를 불러오는 중"}</span>}
    {!wide && <figcaption>업로드한 증빙</figcaption>}
  </figure>;
}
