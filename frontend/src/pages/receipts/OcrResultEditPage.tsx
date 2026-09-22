import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { mockOcrResult } from "../../mocks/ocr";
import { mockDeduction } from "../../mocks/deduction";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

export function OcrResultEditPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const fmt = useMaskedFormat();
  const [supplierName, setSupplierName] = useState(mockOcrResult.supplierName);
  const [businessNumber, setBusinessNumber] = useState(mockOcrResult.supplierBusinessNumber);
  const [itemName, setItemName] = useState(mockOcrResult.itemName);
  const [supplyAmount, setSupplyAmount] = useState(mockOcrResult.supplyAmount.toLocaleString("ko-KR"));
  const [issuedAt, setIssuedAt] = useState(mockOcrResult.issuedAt);

  return (
    <div className="page">
      <PageHeader title="추출 결과 확인 및 수정" showAmountToggle />
      <div className="page__body">
        <div className="banner banner--info" style={{ marginBottom: 12 }}>
          <span>✨</span>
          <div>
            <div className="banner__title">의제매입세액공제 케이스 감지</div>
            면세농산물(생닭)이 포함된 매입 영수증입니다. 의제매입세액공제율(음식점업 2/102)이 자동 적용되었습니다. 수치를 반드시 확인하세요.
          </div>
        </div>

        <div className="banner banner--warning" style={{ marginBottom: 20 }}>
          <span>⚠️</span>
          <div>OCR 인식 오류가 발생할 수 있습니다. 실물 영수증과 대조 후 오류를 수정해 주세요.</div>
        </div>

        <div style={{ fontWeight: 700, marginBottom: 12 }}>추출된 면세농산물 매입계산서 정보</div>

        <div className="form-field">
          <label className="form-field__label">공급자 상호</label>
          <input className="input" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label">공급자 사업자등록번호</label>
          <input className="input" value={businessNumber} onChange={(e) => setBusinessNumber(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label">품목명 (면세품목)</label>
          <input className="input" value={itemName} onChange={(e) => setItemName(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label">매입 공급가액 (면세)</label>
          <input className="input" value={supplyAmount} onChange={(e) => setSupplyAmount(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label">부가가치세</label>
          <input className="input" value="0 원 (면세품목)" disabled />
        </div>
        <div className="form-field">
          <label className="form-field__label">발행 일자</label>
          <input className="input" type="date" value={issuedAt} onChange={(e) => setIssuedAt(e.target.value)} />
        </div>

        <div className="card" style={{ marginTop: 8 }}>
          <div className="card__title">🧮 의제매입세액 자동 계산 결과</div>
          <div className="field-row">
            <span className="field-row__label">면세 매입 공급가액</span>
            <span className="field-row__value">{fmt.won(mockDeduction.exemptSupplyAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">적용 공제율 (음식점업)</span>
            <span className="field-row__value field-row__value--accent">{mockDeduction.applicableRate}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">공제 가능 의제매입세액</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockDeduction.deductibleAmount)}
            </span>
          </div>
        </div>

        <div className="stack-gap-sm" style={{ marginTop: 24 }}>
          <button className="btn btn--primary" onClick={() => navigate(`/receipts/${id}/analysis`)}>
            수정 완료 및 의제매입세액 반영
          </button>
          <button className="btn btn--secondary" onClick={() => navigate("/capture")}>
            다시 촬영하기
          </button>
        </div>
      </div>
    </div>
  );
}
