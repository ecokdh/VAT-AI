import test from "node:test";
import assert from "node:assert/strict";
import { inPeriod, needsReview, summarizeReview } from "../src/hooks/reviewState.ts";
const row = (overrides={}) => ({ direction:"purchase", state:"confirmed", review_status:"analyzed", transaction_date:"2026-09-11", deleted_at:null, ...overrides });
test("신고 기간의 경계와 다른 연도를 구분한다", () => {
  assert.equal(inPeriod("2026-06-30","2026-H1"),true);
  assert.equal(inPeriod("2026-07-01","2026-H1"),false);
  assert.equal(inPeriod("2026-07-01","2026-H2"),true);
  assert.equal(inPeriod("2025-09-11","2026-YEAR"),false);
  assert.equal(inPeriod("2026-03-31","2026-Q1"),true);
  assert.equal(inPeriod("2026-04-01","2026-Q1"),false);
  assert.equal(inPeriod("2026-06-30","2026-Q3"),false);
  assert.equal(inPeriod("2026-09-30","2026-Q3"),true);
  assert.equal(inPeriod("2026-10-01","2026-Q3"),false);
});
test("확정 매출에는 매입 공제 분석을 요구하지 않는다", () => {
  assert.equal(needsReview(row({direction:"sales",review_status:"not_analyzed"})),false);
  assert.equal(needsReview(row({direction:"sales",state:"draft"})),true);
  assert.equal(needsReview(row({review_status:"caution"})),true);
  assert.equal(needsReview(row({review_status:"excluded"})),false);
});
test("미확정·보류를 중복 집계하지 않고 삭제·다른 기간 거래를 제외한다", () => {
  const summary=summarizeReview([row(),row({state:"draft"}),row({review_status:"stale"}),row({direction:"sales",review_status:"not_analyzed"}),row({deleted_at:"2026-10-01"}),row({transaction_date:"2026-01-01"})],[{date:"2026-09-01",direction:"sales"}],"2026-H2");
  assert.deepEqual(summary,{total:5,unconfirmed:2,pending:1,ready:2,firstDirection:"sales"});
});
