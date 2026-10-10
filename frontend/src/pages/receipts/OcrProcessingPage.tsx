import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { getReceipt, retryReceiptOcr, type ReceiptProcessingApi } from "../../api/receipts";

const stages = [
  ["photo_quality", "사진 품질 확인"],
  ["text_recognition", "증빙 글자 인식"],
  ["transaction_extraction", "거래 정보 · 금액 구분"],
  ["missing_field_check", "누락 · 오독 항목 확인"],
] as const;

function stageLabel(status?: string) {
  if (status === "completed") return "완료";
  if (status === "processing") return "진행 중";
  if (status === "failed") return "확인 필요";
  if (status === "skipped") return "건너뜀";
  return "대기";
}

export function OcrProcessingPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [receipt, setReceipt] = useState<ReceiptProcessingApi | null>(null);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [pollVersion, setPollVersion] = useState(0);

  useEffect(() => {
    if (!id) return;
    let active = true;
    let timer: number | undefined;

    async function loadReceipt() {
      try {
        const result = await getReceipt(Number(id));
        if (!active) return;
        setReceipt(result);
        if (result.status === "processing") {
          timer = window.setTimeout(() => void loadReceipt(), 900);
        } else if (result.status === "done") {
          timer = window.setTimeout(() => navigate(`/receipts/${id}/review`, { replace: true }), 700);
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
  }, [id, navigate, pollVersion]);

  const failed = receipt?.status === "failed";
  const complete = receipt?.status === "done";
  const progress = receipt?.processing_progress ?? 0;

  async function retrySamePhoto() {
    if (!id) return;
    setRetrying(true);
    setError("");
    try {
      await retryReceiptOcr(Number(id));
      setReceipt((current) => current ? { ...current, status: "processing" } : current);
      setPollVersion((version) => version + 1);
    } catch (cause) {
      setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "재분석을 시작하지 못했습니다." : "재분석을 시작하지 못했습니다.");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="page">
      <div className="page__body" style={{ paddingTop: 36 }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--color-primary)" }}>증빙 분석</div>
          <div style={{ fontSize: 24, fontWeight: 800, marginTop: 20 }}>
            {failed ? "증빙 분석을 마치지 못했어요" : complete ? "증빙 분석이 끝났어요" : "증빙 분석 중"}
          </div>
          <div className="muted" style={{ fontSize: 14, marginTop: 8 }}>
            {failed ? "원본 증빙과 함께 추출 결과를 확인해 주세요." : "증빙의 거래 정보와 금액을 읽고 있어요."}
          </div>
        </div>

        <div className="card" style={{ marginTop: 26, padding: 18 }}>
          {stages.map(([key, label]) => {
            const status = receipt?.stage_statuses[key] ?? "pending";
            return (
              <div className="field-row" key={key} style={{ minHeight: 54 }}>
                <span className="field-row__label" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span aria-hidden="true" style={{ color: status === "completed" ? "#1473e6" : "#76839a" }}>
                    {status === "completed" ? "✓" : status === "processing" ? "◌" : status === "failed" ? "!" : "○"}
                  </span>
                  {label}
                </span>
                <span className="field-row__value" style={{ color: status === "failed" ? "#b54708" : undefined }}>
                  {stageLabel(status)}
                </span>
              </div>
            );
          })}
          <div style={{ marginTop: 14, height: 8, borderRadius: 8, background: "#e5edf9", overflow: "hidden" }}>
            <div style={{ width: `${progress}%`, height: "100%", borderRadius: 8, background: "#1473e6", transition: "width 250ms ease" }} />
          </div>
          <div className="muted" style={{ textAlign: "center", marginTop: 10, fontSize: 13 }}>
            {complete ? "보관함에서 추출 결과를 확인할 수 있어요." : failed ? "인식되지 않은 항목은 직접 확인할 수 있어요." : "증빙 정보를 분석하고 있어요…"}
          </div>
        </div>

        {receipt && (receipt.vendor || receipt.amount != null || receipt.date) && (
          <div className="card" style={{ marginTop: 18 }}>
            <div className="field-row"><span className="field-row__label">거래처</span><span className="field-row__value">{receipt.vendor ?? "확인 필요"}</span></div>
            <div className="field-row"><span className="field-row__label">금액</span><span className="field-row__value">{receipt.amount?.toLocaleString("ko-KR") ?? "확인 필요"}</span></div>
            <div className="field-row"><span className="field-row__label">거래일</span><span className="field-row__value">{receipt.date ?? "확인 필요"}</span></div>
          </div>
        )}

        {receipt?.ocr_warnings.map((warning) => (
          <div className="banner banner--warning" style={{ marginTop: 14 }} key={warning}>{warning}</div>
        ))}
        {error && <div className="banner banner--error" style={{ marginTop: 20 }} role="alert">{error}</div>}

        {failed && <div className="stack-gap-sm" style={{ marginTop: 24 }}>
          {receipt.ocr_user_attempts < 2 ? (
            <button className="btn btn--primary" style={{ width: "100%" }} disabled={retrying} onClick={() => void retrySamePhoto()}>
              {retrying ? "재분석 준비 중" : "같은 사진으로 한 번 더 분석"}
            </button>
          ) : (
            <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => navigate("/capture", { replace: true })}>
              새로 촬영하기
            </button>
          )}
          <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate("/storage/purchase")}>
            보관함으로 돌아가기
          </button>
        </div>}
      </div>
    </div>
  );
}
