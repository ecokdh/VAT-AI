import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { Icon } from "../components/Icon";
import { getMe, markOcrGuideSeen } from "../api/auth";
import { CaptureGuide } from "../components/CaptureGuide";
import { enqueueReceiptOcr } from "../api/receipts";

export function CapturePage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const direction = params.get("direction");
  const hasDirection = direction === "purchase" || direction === "sales";
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
  useEffect(()=>{
    if(!hasDirection)return;
    let active=true;
    getMe().then(user=>{if(active)setGuide(user.ocr_guide_seen?"ready":"show");}).catch(()=>{if(active)setGuide("error");});
    return()=>{active=false;};
  },[hasDirection]);
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
    if (!hasDirection || guide !== "ready" || pendingFile) return;
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
  }, [facingMode, hasDirection, guide, pendingFile]);

  async function uploadAndNavigate(file: File) {
    if (direction !== "purchase" && direction !== "sales") return;
    setError("");
    setIsUploading(true);
    try {
      const receipt = await enqueueReceiptOcr(file, direction);
      navigate(`/receipts/${receipt.receipt_id}/processing`, { replace: true });
    } catch (requestError) {
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

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setError("촬영에 실패했습니다. 다시 시도해주세요.");
          return;
        }
        const file = new File([blob], `receipt-${Date.now()}.jpg`, { type: "image/jpeg" });
        setPendingFile(file);
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

  if (!hasDirection) return <div className="page"><PageHeader title="증빙 등록" /><div className="page__body">
    <h1 className="screen-title">어떤 거래의 증빙인가요?</h1><p className="muted">보관할 곳을 선택한 뒤 촬영하거나 파일을 올려주세요.</p>
    <div className="stack-gap-sm" style={{ marginTop: 28 }}>{(["purchase", "sales"] as const).map((value) => <button className="card capture-choice" key={value} onClick={() => setParams({ direction: value })}><Icon name="folder" size={30} /><span><strong>{value === "purchase" ? "매입" : "매출"}</strong><small>{value === "purchase" ? "사업을 위해 지출한 거래" : "고객에게 판매한 거래"}</small></span><span>›</span></button>)}</div>
  </div></div>;

  if(guide!=="ready")return <div className="page qa-page"><PageHeader title="증빙 촬영 안내" onBack={()=>navigate(`/storage/${direction}`)}/>{guide==="show"?<CaptureGuide seconds={seconds}/>:<div className="page__body">{guide==="error"?<p className="banner banner--error">촬영 안내 정보를 불러오지 못했습니다. 로그인 상태를 확인하고 다시 시도해 주세요.</p>:<p role="status">촬영을 준비하고 있습니다.</p>}</div>}</div>;
  if(pendingFile)return <div className="page qa-page"><PageHeader title="촬영한 증빙 확인" onBack={()=>setPendingFile(null)}/><main className="page__body"><h1 className="screen-title">글자가 선명하게 보이나요?</h1><p className="muted">영수증 전체가 보이고 금액·날짜를 읽을 수 있는지 확인해 주세요.</p><img className="capture-preview" src={preview} alt="분석할 증빙 미리보기"/>{error&&<p className="banner banner--error" role="alert">{error}</p>}<div className="btn-row"><button className="btn btn--secondary" disabled={isUploading} onClick={()=>{setPendingFile(null);setError("");}}>다시 촬영·선택</button><button className="btn btn--primary" disabled={isUploading} onClick={()=>void uploadAndNavigate(pendingFile)}>{isUploading?"올리는 중…":"선명해요 · 분석하기"}</button></div></main></div>;
  return (
    <div className="page" style={{ background: "#0c0c10" }}>
      <header className="page-header" style={{ background: "transparent" }}>
        <button className="icon-btn" style={{ color: "#fff" }} aria-label="보관함으로 돌아가기" onClick={() => navigate(`/storage/${direction}`)}>
          ‹
        </button>
        <span className="page-header__title" style={{ color: "#fff" }}>
          {direction === "purchase" ? "매입" : "매출"} 증빙 촬영
        </span>
        <span className="icon-btn" style={{ color: "#fff" }}>
          ⚡
        </span>
      </header>

      <div
        style={{
          flex: 1,
          position: "relative",
          margin: "0 20px",
          borderRadius: 16,
          aspectRatio: "3 / 4",
          maxHeight: 640,
          overflow: "hidden",
          background: "#000",
        }}
      >
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
        <canvas ref={canvasRef} style={{ display: "none" }} />

        <div
          style={{
            position: "absolute",
            inset: 0,
            border: "2px dashed rgba(61,90,254,0.9)",
            borderRadius: 16,
            pointerEvents: "none",
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            paddingBottom: 16,
          }}
        >
          <div
            style={{
              background: "rgba(0,0,0,0.65)",
              color: "#fff",
              fontSize: 13,
              padding: "10px 16px",
              borderRadius: 999,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            ⬚ 어두운 배경 · 전체가 보이게 · 초점 맞추기
          </div>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />

      {error && (
        <div className="banner banner--error" style={{ margin: "0 20px" }}>
          <span>⚠️</span>
          <div>{error}</div>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", padding: "28px 20px 40px" }}>
        <CaptureControl icon="▧" label="앨범 및 파일 선택" onClick={openFilePicker} disabled={isUploading} />
        <button
          onClick={captureFromVideo}
          disabled={isUploading || !cameraReady}
          style={{
            width: 76,
            height: 76,
            borderRadius: "50%",
            border: "4px solid #fff",
            background: "transparent",
          }}
          aria-label="촬영"
        >
          {isUploading ? "…" : ""}
        </button>
        <CaptureControl icon="🔄" label="카메라 전환" onClick={toggleCamera} disabled={isUploading} />
      </div>
    </div>
  );
}

function CaptureControl({
  icon,
  label,
  onClick,
  disabled = false,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: "#fff" }}
    >
      <span
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          background: "rgba(255,255,255,0.15)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 20,
        }}
      >
        {icon}
      </span>
      <span style={{ fontSize: 12 }}>{label}</span>
    </button>
  );
}
