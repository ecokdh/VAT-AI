import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { getMe, markOcrGuideSeen } from "../api/auth";
import { CaptureGuide } from "../components/CaptureGuide";
import { enqueueReceiptOcr, getReceipt, retryReceiptOcr, type ReceiptProcessingApi } from "../api/receipts";
import "../styles/capture.css";

export function CapturePage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // 증빙 촬영은 매입 영수증만 받는다.
  const backToStorage = "/storage/purchase";
  const fileOnly = params.get("source") === "file";
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const [cameraReady, setCameraReady] = useState(false);
  const [guide,setGuide] = useState<"loading"|"show"|"ready"|"error">("loading");
  const [seconds,setSeconds] = useState(3);
  const [pendingFile,setPendingFile] = useState<File|null>(null);
  const [preview,setPreview] = useState("");
  // 셔터를 누르면 찍은 화면을 멈춰 보여 주고 그 위에서 바로 인식을 시작한다.
  const [frozen,setFrozen] = useState("");
  // 올린 영수증의 인식 진행을 이 화면 위에서 따라간다(게이지·결과 안내).
  const [receipt,setReceipt] = useState<ReceiptProcessingApi|null>(null);
  const [receiptId,setReceiptId] = useState<number|null>(null);
  const [poll,setPoll] = useState(0);
  useEffect(()=>{
    if(receiptId===null)return;
    let active=true, timer:number|undefined;
    const load=()=>getReceipt(receiptId).then(result=>{
      if(!active)return;
      setReceipt(result);
      if(result.status==="processing")timer=window.setTimeout(load,900);
      else if(result.status==="done"||result.status==="needs_edit")navigate(`/receipts/${receiptId}/review`,{replace:true});
    }).catch(()=>{if(active)setReceipt(current=>current&&{...current,status:"failed"});});
    void load();
    return()=>{active=false;window.clearTimeout(timer);};
  },[receiptId,poll,navigate]);
  function resetCapture(){setFrozen("");setReceipt(null);setReceiptId(null);setError("");}
  async function retrySamePhoto(){
    if(receiptId===null)return;
    try{await retryReceiptOcr(receiptId);setReceipt(current=>current&&{...current,status:"processing"});setPoll(v=>v+1);}
    catch(cause){setError(isAxiosError(cause)?cause.response?.data?.error?.message??"다시 분석하지 못했어요.":"다시 분석하지 못했어요.");}
  }
  useEffect(()=>{
    let active=true;
    getMe().then(user=>{if(active)setGuide(user.ocr_guide_seen?"ready":"show");}).catch(()=>{if(active)setGuide("error");});
    return()=>{active=false;};
  },[]);
  useEffect(()=>{
    if(guide!=="show")return;
    const tick=window.setInterval(()=>setSeconds(value=>Math.max(0,value-1)),1000);
    const timer=window.setTimeout(()=>{void markOcrGuideSeen().catch(()=>{});setGuide("ready");},3000);
    return()=>{window.clearInterval(tick);window.clearTimeout(timer);};
  },[guide]);
  useEffect(()=>{
    if(!pendingFile){setPreview("");return;}
    const url=URL.createObjectURL(pendingFile);setPreview(url);
    return()=>URL.revokeObjectURL(url);
  },[pendingFile]);

  // 카메라 스트림 시작/정리 — facingMode가 바뀔 때마다 재실행됨
  useEffect(() => {
    // 인식 중(찍은·고른 사진을 띄운 동안)에는 카메라를 켜지 않는다.
    if (guide !== "ready" || pendingFile || fileOnly || frozen) return;
    let cancelled = false;

    async function startCamera() {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      setCameraReady(false);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: facingMode } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraReady(true);
      } catch {
        if (!cancelled) {
          setError("카메라를 켤 수 없습니다. 브라우저 카메라 권한을 확인해주세요.");
        }
      }
    }

    startCamera();

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [facingMode, guide, pendingFile, fileOnly, frozen]);

  async function upload(file: File) {
    setError("");
    setIsUploading(true);
    try {
      const job = await enqueueReceiptOcr(file, "purchase");
      setReceiptId(job.receipt_id);
    } catch (requestError) {
      setFrozen("");
      const message = isAxiosError(requestError)
        ? requestError.response?.data?.error?.message
        : undefined;
      setError(message ?? "영수증 업로드에 실패했습니다.");
    } finally {
      setIsUploading(false);
    }
  }

  // "촬영" 버튼 — 지금 화면에 보이는 비디오 프레임 한 장을 캡처
  function captureFromVideo() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !cameraReady) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    setFrozen(canvas.toDataURL("image/jpeg", 0.6));

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setFrozen("");
          setError("촬영에 실패했습니다. 다시 시도해주세요.");
          return;
        }
        void upload(new File([blob], `receipt-${Date.now()}.jpg`, { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92
    );
  }

  // "앨범에서 선택" — 기존 방식 그대로 유지 (미리 찍어둔 사진 불러오기용)
  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setPendingFile(file);
  }

  function openFilePicker() {
    fileInputRef.current?.click();
  }

  function toggleCamera() {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  }

  if(guide!=="ready")return <div className="page qa-page"><PageHeader title="증빙 촬영 안내" onBack={()=>navigate(backToStorage)}/>{guide==="show"?<CaptureGuide seconds={seconds}/>:<div className="page__body">{guide==="error"?<p className="banner banner--error">촬영 안내 정보를 불러오지 못했습니다. 로그인 상태를 확인하고 다시 시도해 주세요.</p>:<p role="status">촬영을 준비하고 있습니다.</p>}</div>}</div>;
  if(pendingFile)return <div className="page qa-page capture-confirm"><PageHeader title="촬영한 증빙 확인" onBack={()=>setPendingFile(null)}/><main className="page__body"><h1 className="screen-title">글자가 선명하게 보이나요?</h1><p className="muted">영수증 전체가 보이고 금액·날짜를 읽을 수 있는지 확인해 주세요.</p><img className="capture-preview" src={preview} alt="분석할 증빙 미리보기"/>{error&&<p className="banner banner--error" role="alert">{error}</p>}<div className="btn-row"><button className="btn btn--secondary" disabled={isUploading} onClick={()=>{setPendingFile(null);setError("");}}>다시 촬영·선택</button><button className="btn btn--primary" disabled={isUploading} onClick={()=>{setFrozen(URL.createObjectURL(pendingFile));setPendingFile(null);void upload(pendingFile);}}>{isUploading?"증빙 분석 중…":"선명해요 · 분석하기"}</button></div></main></div>;
  if(fileOnly)return <div className="page qa-page"><PageHeader title="영수증 사진 선택" onBack={()=>navigate(backToStorage)}/><main className="page__body"><h1 className="screen-title">다른 영수증 사진을 선택해 주세요</h1><p className="muted">영수증 전체와 금액·날짜가 선명하게 보이는 사진을 선택해 주세요.</p><input ref={fileInputRef} type="file" accept="image/jpeg,image/png" onChange={handleFileChange} style={{display:'none'}}/><button className="btn btn--primary" onClick={openFilePicker}>앨범 및 파일 선택</button><button className="btn btn--secondary" onClick={()=>setParams(previous => { const next = new URLSearchParams(previous); next.delete("source"); return next; })}>직접 촬영하기</button></main></div>;
  const progress = receipt?.status === "processing" ? receipt.processing_progress : receipt ? 100 : 5;
  const canRetry = (receipt?.ocr_user_attempts ?? 2) < 2;
  const outcome = receipt?.status === "unsupported" ? { title: "영수증이 아닌 것 같아요", description: receipt.guide_message || "인쇄된 구매 영수증만 인식할 수 있어요.", icon: "M6 3h12v18l-3-2-3 2-3-2-3 2zM4 4l16 16", canRetry }
    : receipt?.status === "retake" ? { title: "사진을 다시 찍어 주세요", description: receipt.guide_message || "영수증 전체가 선명하게 나오게 찍어 주세요.", icon: "M4 8h3l2-3h6l2 3h3v11H4zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6", canRetry: false }
    : receipt?.status === "failed" ? { title: "인식을 마치지 못했어요", description: "일시적인 오류예요. 다시 시도할 수 있어요.", icon: "M12 4l9 16H3zM12 10v4M12 17v.01", canRetry }
    : null;

  return (
    <div className="capture-page">
      <video ref={videoRef} className="capture-video" autoPlay muted playsInline />
      <canvas ref={canvasRef} hidden />
      {frozen && <img className="capture-video" src={frozen} alt="" />}
      <div className="capture-guide-frame" aria-hidden="true"><i /><i /><i /><i /></div>
      <div className="capture-top">
        <button className="capture-square" aria-label="보관함으로 돌아가기" onClick={() => navigate(backToStorage)}><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg></button>
        <span className="capture-title">매입 영수증 촬영</span>
        <span className="capture-square capture-square--ghost" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M13 3L5 13h6l-1 8 8-10h-6z" /></svg></span>
      </div>
      {!frozen && <p className="capture-hint">영수증 전체가 모서리 안에 들어오게</p>}
      {error && <p className="banner banner--error capture-error" role="alert">{error}</p>}
      <input ref={fileInputRef} type="file" accept="image/jpeg,image/png" onChange={handleFileChange} hidden />
      <div className="capture-controls">
        <CaptureControl label="앨범" path="M4 6h16v12H4zM4 15l5-5 4 4 3-3 4 4M15 9.5h.01" onClick={openFilePicker} disabled={isUploading} />
        <button className="capture-shutter" onClick={captureFromVideo} disabled={isUploading || !cameraReady} aria-label="촬영"><i /></button>
        <CaptureControl label="전환" path="M4 12a8 8 0 0 1 14-5.3M20 4v4h-4M20 12a8 8 0 0 1-14 5.3M4 20v-4h4" onClick={toggleCamera} disabled={isUploading} />
      </div>
      {frozen && (outcome
        ? <div className="capture-result" role="alert">
            <span className={`capture-result__icon capture-result__icon--${receipt?.status}`}><svg viewBox="0 0 24 24"><path d={outcome.icon} /></svg></span>
            <h2>{outcome.title}</h2>
            <p>{outcome.description}</p>
            {error && <p className="capture-result__error">{error}</p>}
            {outcome.canRetry
              ? <button className="btn btn--primary" onClick={() => void retrySamePhoto()}>같은 사진으로 한 번 더 분석</button>
              : <button className="btn btn--primary" onClick={resetCapture}>다시 촬영하기</button>}
            <button className="btn capture-result__secondary" onClick={() => navigate("/dashboard")}>메인 화면으로 돌아가기</button>
          </div>
        : <div className="capture-processing" role="status">
            <div className="capture-processing__pill">
              <div className="capture-progress__row"><span>인식 중</span><span>{progress}%</span></div>
              <div className="capture-progress"><i style={{ width: `${progress}%` }} /></div>
            </div>
          </div>)}
    </div>
  );
}

function CaptureControl({ label, path, onClick, disabled = false }: { label: string; path: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button className="capture-control" onClick={onClick} disabled={disabled}>
      <span><svg viewBox="0 0 24 24"><path d={path} /></svg></span>
      {label}
    </button>
  );
}
