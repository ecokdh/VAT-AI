import type { Deduction } from "../types";
import { processingReceipt } from "./receipts";

export const mockDeduction: Deduction = {
  receiptId: processingReceipt.id,
  isDeductible: true,
  reason:
    "음식점업을 영위하는 일반과세자가 면세 농산물(생닭)을 매입한 경우, 부가가치세법 제42조에 따라 의제매입세액공제 적용이 가능합니다.",
  relatedLaws: [
    {
      title: "부가가치세법 제42조",
      content:
        "의제매입세액 공제: 사업자가 면세로 공급받은 농·축·수·임산물을 원재료로 하여 제조·가공한 재화 또는 창출한 용역을 공급하는 경우, 해당 면세농산물 구입가액에 공제율을 곱한 금액을 매입세액으로 공제한다.",
    },
    {
      title: "부가가치세법 시행령 제84조",
      content: "공제율 세분화: 음식점업의 경우 과세표준 2억 원 이하 사업자는 2/102, 초과 사업자는 1/102를 적용한다.",
    },
    {
      title: "국세청 예규 부가 2023-07",
      content: "면세농산물 구매 시 의제매입세액공제 한도는 과세기간 매출세액의 50%(음식점업 개인사업자 기준)를 초과할 수 없다.",
    },
  ],
  applicableRate: "2/102",
  deductibleAmount: 40_000,
  exemptSupplyAmount: 2_040_000,
  capWarning: "이번 과세기간 누적 의제매입세액 공제액이 매출세액의 50% 한도(2,250,000원)에 근접하고 있습니다. 한도 초과분은 공제되지 않습니다.",
};
