import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { getReceipt, retryReceiptOcr, type ReceiptProcessingApi } from "../../api/receipts";
import { ReceiptPreview } from "../../components/ReceiptPreview";
import { RecognitionDetails } from "../../components/RecognitionDetails";

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
        } else if (result.status === "done" && !result.ocr_missing_fields?.length && !result.ocr_warnings?.length) {
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
  const unsupported = receipt?.status === "unsupported";
  const retake = receipt?.status === "retake";
  const needsEdit = receipt?.status === "needs_edit" || (receipt?.status === "done" && Boolean(receipt.ocr_missing_fields?.length || receipt.ocr_warnings?.length));
  const complete = receipt?.status === "done";
  const isFinal = failed || unsupported || retake || needsEdit || complete;
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

  let statusTitle = "증빙 분석 중";
  let statusDescription = "증빙의 거래 정보와 금액을 읽고 있어요.";

  if (unsupported) {
    statusTitle = "지원하지 않는 문서예요";
    statusDescription = receipt?.guide_message || "현재는 인쇄된 구매 영수증만 지원합니다. 다른 영수증 사진을 선택해 주세요.";
  } else if (retake) {
    statusTitle = "사진을 다시 촬영해 주세요";
    statusDescription = receipt?.guide_message || "사진 판독 문제로 주요 정보를 읽기 어렵습니다. 영수증 전체가 선명하게 나오도록 다시 촬영해 주세요.";
  } else if (failed) {
    statusTitle = "증빙 분석을 마치지 못했어요";
    statusDescription = "통신 또는 일시적인 처리 오류로 분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  } else if (needsEdit || (complete && receipt?.ocr_missing_fields?.length)) {
    statusTitle = "직접 확인할 항목이 있어요";
    statusDescription = receipt?.guide_message || "일부 정보를 확정하지 못했습니다. 원본과 비교해 확인·수정해 주세요.";
  } else if (complete) {
    statusTitle = "증빙 분석이 끝났어요";
    statusDescription = "원본 사진과 비교해 추출 결과를 확인해 주세요.";
  }

  return (
    <div className="page processing-page">
      <div className="page__body">
        <div className="processing-intro">
          <div className="processing-eyebrow">증빙 분석</div>
          {!isFinal && <div className="ocr-loading-spinner" aria-label="분석 진행 중" />}
          <h1>{statusTitle}</h1>
          <p className="muted">{statusDescription}</p>
        </div>

        {id && <ReceiptPreview key={id} id={Number(id)} wide />}
        {!unsupported && !retake && !failed && <RecognitionDetails result={receipt?.recognition} />}

        <div className="card processing-timeline">
          {stages.map(([key, label]) => {
            const status = receipt?.stage_statuses[key] ?? "pending";
            return (
              <div className={`field-row processing-stage processing-stage--${status}`} key={key}>
                <span className="field-row__label">
                  <span className="processing-stage__marker" aria-hidden="true" />
                  {label}
                </span>
                <span className="field-row__value">{stageLabel(status)}</span>
              </div>
            );
          })}
          <div className="processing-progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="muted processing-note">
            {unsupported ? "현재는 인쇄된 구매 영수증만 지원합니다." :
             retake ? "선명하고 전체가 보이는 사진으로 다시 시도해 주세요." :
             needsEdit ? "읽은 정보를 확인하고 필요한 항목을 수정해 주세요." :
             complete ? "추출 결과를 확인해 주세요." :
             failed ? "일시적인 오류입니다. 다시 시도할 수 있어요." :
             "증빙 정보를 분석하고 있어요…"}
          </div>
        </div>

        {receipt && (receipt.vendor || receipt.amount != null || receipt.date) && !unsupported && !retake && (
          <div className="card" style={{ marginTop: 18 }}>
            <div className="field-row"><span className="field-row__label">거래처</span><span className="field-row__value">{receipt.vendor ?? "확인 필요"}</span></div>
            <div className="field-row"><span className="field-row__label">금액</span><span className="field-row__value">{receipt.amount?.toLocaleString("ko-KR") ?? "확인 필요"}</span></div>
            <div className="field-row"><span className="field-row__label">거래일</span><span className="field-row__value">{receipt.date ?? "확인 필요"}</span></div>
          </div>
        )}

        {(unsupported || retake) && (
          <div className="banner banner--warning" style={{ marginTop: 18 }}>
            {statusDescription}
          </div>
        )}

        {!unsupported && !retake && receipt?.ocr_warnings.map((warning) => (
          <div className="banner banner--warning" style={{ marginTop: 14 }} key={warning}>{warning}</div>
        ))}
        {error && <div className="banner banner--error" style={{ marginTop: 20 }} role="alert">{error}</div>}

        {unsupported && (
          <div className="stack-gap-sm" style={{ marginTop: 24 }}>
            <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => navigate(`/capture?direction=${receipt.direction}&source=file`, { replace: true })}>
              다른 사진 선택
            </button>
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/storage/${receipt.direction}`)}>
              보관함으로 돌아가기
            </button>
          </div>
        )}

        {retake && (
          <div className="stack-gap-sm" style={{ marginTop: 24 }}>
            <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => navigate(`/capture?direction=${receipt.direction}`, { replace: true })}>
              다시 촬영하기
            </button>
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/capture?direction=${receipt.direction}&source=file`, { replace: true })}>
              다른 사진 선택
            </button>
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/storage/${receipt.direction}`)}>
              보관함으로 돌아가기
            </button>
          </div>
        )}

        {needsEdit && (
          <div className="stack-gap-sm" style={{ marginTop: 24 }}>
            <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => navigate(`/receipts/${id}/review`, { replace: true })}>
              읽은 정보 확인 · 수정
            </button>
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/capture?direction=${receipt.direction}&source=file`, { replace: true })}>
              다른 사진 선택
            </button>
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/storage/${receipt.direction}`)}>
              보관함으로 돌아가기
            </button>
          </div>
        )}

        {failed && (
          <div className="stack-gap-sm" style={{ marginTop: 24 }}>
            {receipt.ocr_user_attempts < 2 ? (
              <button className="btn btn--primary" style={{ width: "100%" }} disabled={retrying} onClick={() => void retrySamePhoto()}>
                {retrying ? "재분석 준비 중" : "같은 사진으로 한 번 더 분석"}
              </button>
            ) : (
              <button className="btn btn--primary" style={{ width: "100%" }} onClick={() => navigate(`/capture?direction=${receipt.direction}`, { replace: true })}>
                새로 촬영하기
              </button>
            )}
            <button className="btn btn--secondary" style={{ width: "100%" }} onClick={() => navigate(`/storage/${receipt?.direction ?? "purchase"}`)}>
              보관함으로 돌아가기
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
