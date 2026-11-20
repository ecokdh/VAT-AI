import { formatWon } from "../utils/format";

export type DuplicateSide = {
  source?: string;
  document_id: number | null;
  row_index: number | null;
  label: string;
  date?: string | null;
  supply_amount: number;
  vat_amount: number;
  fee_amount?: number | null;
  total_amount: number;
  note?: string | null;
  reference?: string | null;
  identity_last4?: string | null;
  counterparty?: string | null;
  scope?: string | null;
};

export type DuplicateDetails = {
  match_kind: "exact_6_fields" | "core_5_fields" | "month_amount" | "reference";
  matched_fields: string[];
  invoice: DuplicateSide;
  counterpart: DuplicateSide;
};

export type FilingIssue = {
  issue_id: string;
  reason_code: string;
  source?: string | null;
  input_key?: string | null;
  impact_amount?: number | null;
  question: string;
  details?: DuplicateDetails;
};

export type DeduplicatedRow = {
  issue_id?: string;
  reason: string;
  source_document?: number | null;
  source_row?: number | null;
  excluded_total_amount: number;
  details?: DuplicateDetails;
};

export type SavedFeedback = {
  request_id: string;
  issue_id: string;
  action: string;
  evidence: string;
  amount?: number | null;
};

function SideCard({
  badge,
  badgeTone,
  keepLabel,
  dateLabel,
  side,
  showFee,
}: {
  badge: string;
  badgeTone: "cash" | "invoice";
  keepLabel?: string;
  dateLabel: string;
  side: DuplicateSide;
  showFee: boolean;
}) {
  return (
    <div className={`dup-side-card dup-side-card--${badgeTone}`}>
      <div className="dup-side-card__head">
        <span className={`dup-badge dup-badge--${badgeTone}`}>{badge}</span>
        {keepLabel && <span className="dup-keep-tag">{keepLabel}</span>}
      </div>
      <dl className="dup-fields">
        <div>
          <dt>{dateLabel}</dt>
          <dd>{side.date ?? "미확인"}</dd>
        </div>
        <div>
          <dt>공급가액</dt>
          <dd>{formatWon(side.supply_amount)}</dd>
        </div>
        <div>
          <dt>부가세</dt>
          <dd>{formatWon(side.vat_amount)}</dd>
        </div>
        {showFee && (
          <div>
            <dt>봉사료</dt>
            <dd>{side.fee_amount == null ? "—" : formatWon(side.fee_amount)}</dd>
          </div>
        )}
        <div className="dup-field-total">
          <dt>총금액</dt>
          <dd>{formatWon(side.total_amount)}</dd>
        </div>
        <div>
          <dt>승인번호</dt>
          <dd className="dup-ref">{side.reference || "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

export function SalesDuplicateCheckPanel({
  issues,
  choices,
  onChoose,
  onSave,
  busy,
}: {
  issues: FilingIssue[];
  choices: Record<string, "O" | "X">;
  onChoose: (issueId: string, choice: "O" | "X") => void;
  onSave: () => void;
  busy: boolean;
}) {
  const chosenCount = issues.filter(issue => choices[issue.issue_id] != null).length;
  const counterpartNames = [...new Set(
    issues.map(issue => (issue.details?.counterpart.label ?? "").replace("홈택스 ", "")).filter(Boolean),
  )];
  const targetLabel = counterpartNames.length === 1 ? counterpartNames[0] : "현금영수증·카드";

  if (!issues.length) return null;

  return (
    <section className="dup-section" aria-label="중복 매출 확인">
      <div className="dup-panel">
          <div className="dup-panel__header">
            <div>
              <h2>중복 매출 확인</h2>
              <p className="dup-panel__subtitle">
                세금계산서와 겹치는 {targetLabel} 내역이 있습니다. 같은 거래라면 {targetLabel}에서만 제외됩니다.
              </p>
            </div>
            <span className="dup-count-pill">{chosenCount} / {issues.length}건</span>
          </div>

          <div className="dup-list">
            {issues.map((issue, index) => {
              const details = issue.details;
              const showFee = (details?.counterpart.fee_amount ?? 0) !== 0 || (details?.invoice.fee_amount ?? 0) !== 0;
              const selected = choices[issue.issue_id];
              const impact = issue.impact_amount ?? details?.counterpart.total_amount ?? 0;
              const counterpartLabel = details?.counterpart.label ?? targetLabel;
              const shortSource = counterpartLabel.replace("홈택스 ", "");

              return (
                <article className="dup-card" key={issue.issue_id}>
                  {issues.length > 1 && (
                    <div className="dup-card__top">
                      <span className="dup-card__index">{index + 1} / {issues.length}건</span>
                    </div>
                  )}

                  {details ? (
                    <div className="dup-compare" data-fee={showFee || undefined}>
                      <SideCard
                        badge={shortSource}
                        badgeTone="cash"
                        dateLabel="날짜"
                        side={details.counterpart}
                        showFee={showFee}
                      />
                      <SideCard
                        badge="매출 세금계산서"
                        badgeTone="invoice"
                        keepLabel="유지"
                        dateLabel="작성일자"
                        side={details.invoice}
                        showFee={showFee}
                      />
                    </div>
                  ) : (
                    <p className="dup-fallback-question">{issue.question}</p>
                  )}

                  <div className="dup-ox-grid" role="group" aria-label={`${index + 1}번 중복 여부 선택`}>
                    <button
                      type="button"
                      className={`dup-ox-btn dup-ox-btn--o${selected === "O" ? " is-selected" : ""}`}
                      aria-pressed={selected === "O"}
                      disabled={busy}
                      onClick={() => onChoose(issue.issue_id, "O")}
                    >
                      <span className="dup-ox-mark" aria-hidden="true">O</span>
                      <strong>중복 맞음</strong>
                      <small>{shortSource}에서 {formatWon(impact)} 제외</small>
                    </button>
                    <button
                      type="button"
                      className={`dup-ox-btn dup-ox-btn--x${selected === "X" ? " is-selected" : ""}`}
                      aria-pressed={selected === "X"}
                      disabled={busy}
                      onClick={() => onChoose(issue.issue_id, "X")}
                    >
                      <span className="dup-ox-mark" aria-hidden="true">X</span>
                      <strong>별개 거래</strong>
                      <small>둘 다 매출에 합산</small>
                    </button>
                  </div>
                </article>
              );
            })}
          </div>

          <button
            type="button"
            className="btn btn--primary dup-save-btn"
            disabled={busy || chosenCount === 0}
            onClick={onSave}
          >
            {busy ? "반영 중..." : chosenCount === issues.length ? "선택 저장하고 금액 반영" : `선택한 ${chosenCount}건 저장`}
          </button>
      </div>
    </section>
  );
}
