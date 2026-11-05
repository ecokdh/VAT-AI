import { useEffect, useState } from "react";

// 증빙 분석 진행 단계. 매입 영수증과 월간 매출 정산서가 같은 화면을 쓴다.
export const STAGES = [
  ["text_recognition", "증빙 글자 인식"],
  ["transaction_extraction", "거래 정보 · 금액 구분"],
  ["missing_field_check", "누락 · 오독 항목 확인"],
] as const;
export type StageStatuses = Partial<Record<string, string>>;
const FINAL_STAGE = new Set(["completed", "failed", "skipped"]);
const PROGRESS_CAP = [30, 60, 90]; // 아직 보여 주지 않은 단계 몫까지 게이지가 먼저 차지 않게 막는다.
const REVEAL_MS = 600;

function stageLabel(status?: string) {
  if (status === "completed") return "완료";
  if (status === "processing") return "진행 중";
  if (status === "failed") return "확인 필요";
  if (status === "skipped") return "건너뜀";
  return "대기";
}

// 한 번 조회했을 때 여러 단계가 이미 끝나 있어도 화면에서는 한 단계씩 차오르게 보여 준다.
// ready는 끝난 단계를 모두 보여 준 뒤에 true가 된다.
export function useStageReveal(statuses: StageStatuses) {
  const [revealed, setRevealed] = useState(0);
  const doneCount = STAGES.findIndex(([key]) => !FINAL_STAGE.has(statuses[key] ?? "pending"));
  const finished = doneCount === -1 ? STAGES.length : doneCount;
  useEffect(() => {
    if (revealed === finished) return;
    const timer = window.setTimeout(() => setRevealed(n => n < finished ? n + 1 : finished), revealed < finished ? REVEAL_MS : 0);
    return () => window.clearTimeout(timer);
  }, [revealed, finished]);
  return { revealed, ready: revealed >= finished, progressCap: PROGRESS_CAP[revealed] ?? 100 };
}

export function ProcessingTimeline({ statuses, revealed, progress, note }: { statuses: StageStatuses; revealed: number; progress: number; note: string }) {
  return <div className="card processing-timeline">
    {STAGES.map(([key, label], index) => {
      const actual = statuses[key] ?? "pending";
      const shown = index < revealed ? actual : index === revealed && actual !== "pending" ? "processing" : "pending";
      return <div className={`field-row processing-stage processing-stage--${shown}`} key={key}>
        <span className="field-row__label"><span className="processing-stage__marker" aria-hidden="true" />{label}</span>
        <span className="field-row__value">{stageLabel(shown)}</span>
      </div>;
    })}
    <div className="processing-progress"><span style={{ width: `${progress}%` }} /></div>
    <div className="muted processing-note">{note}</div>
  </div>;
}
