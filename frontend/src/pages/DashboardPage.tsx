import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { mockUser } from "../mocks/user";
import { mockReport } from "../mocks/report";
import { purchaseTotals, salesTotals } from "../mocks/receipts";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { AmountVisibilityToggle } from "../components/AmountVisibilityToggle";
import { getMe } from "../api/auth";

export function DashboardPage() {
  const navigate = useNavigate();
  const fmt = useMaskedFormat();
  // 스켈레톤 단계: User 엔티티에 사업장명이 아직 없어 대표자명만 실제 로그인 정보로 대체
  const [representativeName, setRepresentativeName] = useState(mockUser.representativeName);

  useEffect(() => {
    if (!localStorage.getItem("access_token")) return;
    getMe()
      .then((me) => setRepresentativeName(me.name))
      .catch(() => {});
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <div className="muted" style={{ fontSize: 13 }}>
            {mockUser.businessName}
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, marginTop: 2 }}>{representativeName}님, 반갑습니다 👋</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <AmountVisibilityToggle />
          <span className="pill pill--primary">{mockUser.taxationType}</span>
        </div>
      </header>

      <div className="page__body">
        <div className="card" style={{ background: "var(--color-surface)", padding: 24 }}>
          <div className="muted" style={{ fontSize: 13 }}>
            2024년 1기 부가가치세 확정 신고 대상
          </div>
          <div style={{ fontWeight: 700, marginTop: 4 }}>예상 납부(환급) 세액</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: "var(--color-primary)", marginTop: 8 }}>
            {fmt.wonSpaced(mockReport.finalTax)}
          </div>
          <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            매출세액에서 매입세액을 공제한 최종 예상 세액
          </div>

          <hr className="summary-card__divider" style={{ borderTopColor: "var(--color-divider)", margin: "18px 0 10px" }} />

          <div className="field-row">
            <span className="field-row__label">🔵 누적 매출세액 (+)</span>
            <span className="field-row__value">{fmt.won(mockReport.salesTax)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">🔴 누적 매입세액 (-)</span>
            <span className="field-row__value">{fmt.won(mockReport.purchaseTaxTotal)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">누적 총 공급가액</span>
            <span className="field-row__value">{fmt.won(mockReport.taxBase)}</span>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 16 }}>
          <QuickAction icon="📷" title="계산서 촬영 (OCR)" subtitle="영수증/계산서 찍어 올리기" onClick={() => navigate("/capture")} />
          <QuickAction icon="💬" title="ChatGPT 세액 상담" subtitle="AI와 실시간 세액 계산법" onClick={() => navigate("/receipts/p_new/analysis")} />
          <QuickAction
            icon="🗂️"
            title="매입 보관함"
            subtitle={`${purchaseTotals.count}건 · ${fmt.won(purchaseTotals.supplyAmount)}`}
            tag="매입"
            onClick={() => navigate("/storage/purchase")}
          />
          <QuickAction
            icon="🗂️"
            title="매출 보관함"
            subtitle={`${salesTotals.thisMonthCount}건 · ${fmt.won(salesTotals.thisMonthSupplyAmount)}`}
            tag="매출"
            onClick={() => navigate("/storage/sales")}
          />
        </div>

        <button
          className="card"
          style={{
            width: "100%",
            marginTop: 16,
            background: "var(--color-primary-light)",
            border: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            textAlign: "left",
          }}
          onClick={() => navigate("/reports")}
        >
          <div>
            <div style={{ color: "var(--color-primary)", fontWeight: 700, fontSize: 13 }}>신고 기한 임박</div>
            <div style={{ fontWeight: 700, marginTop: 4 }}>클릭 한 번으로 부가가치세 신고서 생성</div>
          </div>
          <span
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "var(--color-primary)",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            →
          </span>
        </button>
      </div>
    </div>
  );
}

interface QuickActionProps {
  icon: string;
  title: string;
  subtitle: string;
  tag?: string;
  onClick: () => void;
}

function QuickAction({ icon, title, subtitle, tag, onClick }: QuickActionProps) {
  return (
    <button className="card" style={{ textAlign: "left", position: "relative" }} onClick={onClick}>
      {tag && (
        <span className="pill pill--muted" style={{ position: "absolute", top: 14, right: 14 }}>
          {tag}
        </span>
      )}
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 12,
          background: "var(--color-primary-light)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 18,
          marginBottom: 12,
        }}
      >
        {icon}
      </div>
      <div style={{ fontWeight: 700, fontSize: 15 }}>{title}</div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        {subtitle}
      </div>
    </button>
  );
}
