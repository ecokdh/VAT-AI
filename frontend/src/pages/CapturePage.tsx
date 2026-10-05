import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { uploadReceipt } from "../api/receipts";

export function CapturePage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const [cameraReady, setCameraReady] = useState(false);

  // 카메라 스트림 시작/정리 — facingMode가 바뀔 때마다 재실행됨
  useEffect(() => {
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
  }, [facingMode]);

  async function uploadAndNavigate(file: File) {
    setError("");
    setIsUploading(true);
    try {
      const receipt = await uploadReceipt(file);
      navigate(`/receipts/${receipt.id}/processing`, { replace: true });
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
        void uploadAndNavigate(file);
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
    await uploadAndNavigate(file);
  }

  function openFilePicker() {
    fileInputRef.current?.click();
  }

  function toggleCamera() {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  }

  return (
    <div className="page" style={{ background: "#0c0c10" }}>
      <header className="page-header" style={{ background: "transparent" }}>
        <button className="icon-btn" style={{ color: "#fff" }} onClick={() => navigate(-1)}>
          ‹
        </button>
        <span className="page-header__title" style={{ color: "#fff" }}>
          세금계산서 / 영수증 촬영
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
            ⬚ 사각 가이드라인에 영수증을 맞춰주세요
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
        <CaptureControl icon="🖼️" label="앨범에서 선택" onClick={openFilePicker} disabled={isUploading} />
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