import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { getReceipt, type ReceiptApi } from "../../api/receipts";

export function OcrProcessingPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [receipt, setReceipt] = useState<ReceiptApi | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    let active = true;
    let timer: number | undefined;

    async function loadReceipt() {
      try {
        const result = await getReceipt(Number(id));
        if (!active) return;
        setReceipt(result);
        if (result.status === "done") {
          timer = window.setTimeout(() => navigate("/storage/purchase", { replace: true }), 1200);
        }
      } catch (requestError) {
        if (!active) return;
        const message = isAxiosError(requestError)
          ? requestError.response?.data?.error?.message
          : undefined;
        setError(message ?? "영수증 처리 결과를 불러오지 못했습니다.");
      }
    }

    void loadReceipt();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [id, navigate]);

  const failed = receipt?.status === "failed";

  return (
    <div className="page">
      <div className="page__body" style={{ paddingTop: 48, textAlign: "center" }}>
        <div
          style={{
            width: 88,
            height: 88,
            borderRadius: "50%",
            background: "var(--color-primary-light)",
            margin: "0 auto 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 34,
            animation: "spin 1.4s linear infinite",
          }}
        >
          ✨
        </div>
        <div style={{ fontSize: 20, fontWeight: 800 }}>
          {failed ? "Naver CLOVA OCR 처리 실패" : "Naver CLOVA OCR 분석 결과"}
        </div>
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          {failed ? "영수증은 저장됐지만 OCR 결과를 만들지 못했습니다." : "업로드한 영수증 처리 결과를 확인하고 있습니다."}
        </div>

        <div
          style={{
            marginTop: 28,
            borderRadius: 20,
            overflow: "hidden",
            position: "relative",
            background: "#e9e9ee",
            aspectRatio: "4 / 5",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 48,
              color: "#c3c5d1",
            }}
          >
            🧾
          </div>
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0,0,0,0.7)",
              color: "#fff",
              padding: "12px 16px",
              display: "flex",
              justifyContent: "space-between",
              fontSize: 13,
            }}
          >
            <span>{receipt?.vendor ?? "영수증"}</span>
            <span style={{ color: failed ? "#ff8b8b" : "#7ea0ff", fontWeight: 700 }}>
              {receipt ? (failed ? "실패" : "완료") : "확인 중..."}
            </span>
          </div>
        </div>

        {receipt && (
          <div className="card" style={{ marginTop: 24, textAlign: "left" }}>
            <div className="field-row">
              <span className="field-row__label">상호명</span>
              <span className="field-row__value">{receipt.vendor ?? "인식되지 않음"}</span>
            </div>
            <div className="field-row">
              <span className="field-row__label">금액</span>
              <span className="field-row__value">{receipt.amount?.toLocaleString("ko-KR") ?? "인식되지 않음"}</span>
            </div>
            <div className="field-row">
              <span className="field-row__label">거래일</span>
              <span className="field-row__value">{receipt.date ?? "인식되지 않음"}</span>
            </div>
            <div className="field-row">
              <span className="field-row__label">상태</span>
              <span className="field-row__value">{failed ? "OCR 실패" : "완료"}</span>
            </div>
          </div>
        )}

        {error && (
          <div className="banner banner--error" style={{ marginTop: 24, textAlign: "left" }}>
            <span>⚠️</span>
            <div>{error}</div>
          </div>
        )}

        {failed && (
          <button className="btn btn--secondary" style={{ marginTop: 24 }} onClick={() => navigate("/storage/purchase")}>
            보관함으로 돌아가기
          </button>
        )}
      </div>
    </div>
  );
}
