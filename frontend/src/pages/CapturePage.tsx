import { useRef, useState, type ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { uploadReceipt } from "../api/receipts";

export function CapturePage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

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

  function openFilePicker() {
    fileInputRef.current?.click();
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
          border: "2px dashed rgba(61,90,254,0.9)",
          borderRadius: 16,
          minHeight: 420,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
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
          onClick={openFilePicker}
          disabled={isUploading}
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
        <CaptureControl icon="🔄" label="카메라 전환" onClick={() => {}} />
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
