import test from "node:test";
import assert from "node:assert/strict";
import { inPeriod, isPeriod, periodLabel, periodOptions } from "../src/hooks/reviewState.ts";
import { parentRoute } from "../src/hooks/navigation.ts";

test("2025년 필터는 2026년 거래와 섞이지 않고 정확한 월 범위를 표시한다", () => {
  assert.ok(periodOptions(false).includes("2025-H2"));
  assert.deepEqual(periodOptions(true), ["2026-YEAR", "2025-YEAR"]);
  assert.equal(periodLabel("2025-Q1"), "2025년 1분기 (1~3월)");
  assert.equal(inPeriod("2025-12-31", "2025-H2"), true);
  assert.equal(inPeriod("2026-01-01", "2025-H2"), false);
  assert.equal(isPeriod("2024-H2"), false);
});

test("직접 진입한 화면도 뒤로가기는 상위 화면으로 이동한다", () => {
  assert.equal(parentRoute("/forgot-password"), "/login");
  assert.equal(parentRoute("/reports", "?period=2025-H2"), "/dashboard?period=2025-H2");
  assert.equal(parentRoute("/capture", "?direction=sales"), "/storage/sales");
  assert.equal(parentRoute("/storage/trash", "?direction=sales&period=2026-H2"), "/storage/sales?period=2026-H2");
  assert.equal(parentRoute("/analysis/1"), "/storage/purchase");
});

test("신고서 생성에서 들어간 화면은 뒤로가기로 신고서 생성에 돌아간다", () => {
  assert.equal(parentRoute("/storage/purchase", "?status=review&period=2026-H1&from=reports"), "/reports?period=2026-H1");
  assert.equal(parentRoute("/account", "?period=2026-H1&from=reports"), "/reports?period=2026-H1");
  assert.equal(parentRoute("/storage/purchase", "?period=2026-H1"), "/dashboard?period=2026-H1");
});

test("영수증 전체 보기의 뒤로가기는 보관함으로 이동한다", () => {
  assert.equal(parentRoute("/storage/purchase/receipts", "?period=2026-H1"), "/storage/purchase?period=2026-H1");
  assert.equal(parentRoute("/storage/sales/receipts"), "/storage/sales");
});
