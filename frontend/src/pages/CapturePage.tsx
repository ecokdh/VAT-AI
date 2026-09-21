import { useNavigate } from "react-router-dom";

export function CapturePage() {
  const navigate = useNavigate();

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

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", padding: "28px 20px 40px" }}>
        <CaptureControl icon="🖼️" label="앨범에서 선택" onClick={() => navigate("/receipts/p_new/processing")} />
        <button
          onClick={() => navigate("/receipts/p_new/processing")}
          style={{
            width: 76,
            height: 76,
            borderRadius: "50%",
            border: "4px solid #fff",
            background: "transparent",
          }}
          aria-label="촬영"
        />
        <CaptureControl icon="🔄" label="카메라 전환" onClick={() => {}} />
      </div>
    </div>
  );
}

function CaptureControl({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8, color: "#fff" }}>
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
