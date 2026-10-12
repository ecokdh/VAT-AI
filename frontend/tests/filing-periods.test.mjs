import test from "node:test";
import assert from "node:assert/strict";
import { availablePeriods, choosePeriod } from "../src/hooks/filingPeriods.ts";
import { inPeriod, summarizeReview } from "../src/hooks/reviewState.ts";

test("사업자 형태·과세유형별 기간 및 미입력 제한", () => {
  assert.deepEqual(availablePeriods("individual","general"),["2026-H1","2026-H2"]);
  assert.deepEqual(availablePeriods("corporation","general"),["2026-Q1","2026-H1","2026-Q3","2026-H2"]);
  assert.deepEqual(availablePeriods("individual","simplified"),["2026-YEAR"]);
  for(const [entity,tax] of [[null,"general"],["individual",null],["corporation","simplified"]]) assert.deepEqual(availablePeriods(entity,tax),[]);
});
test("유효 URL·공유 기간을 유지하고 사업자 유형 변경 시 잘못된 선택을 버린다", () => {
  const corporate=availablePeriods("corporation","general");
  assert.equal(choosePeriod(corporate,"2026-Q1","2026-H2"),"2026-Q1");
  assert.equal(choosePeriod(corporate,null,"2026-H1"),"2026-H1");
  assert.equal(choosePeriod(["2026-YEAR"],"2026-H1","2026-Q1"),"2026-YEAR");
  assert.equal(choosePeriod(corporate,null,null,new Date(2026,9,11)),"2026-Q3");
  assert.equal(choosePeriod([],"2026-H1",null),"");
});
test("예정 기간 경계와 신고기간 미선택 집계", () => {
  assert.equal(inPeriod("2026-03-31","2026-Q1"),true);
  assert.equal(inPeriod("2026-04-01","2026-Q1"),false);
  assert.equal(inPeriod("2026-09-30","2026-Q3"),true);
  assert.equal(inPeriod("2026-10-01","2026-Q3"),false);
  assert.equal(inPeriod("2026-10-01",""),false);
  assert.equal(summarizeReview([],[{date:null,direction:"purchase"}],"").total,0);
});
