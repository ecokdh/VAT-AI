export const SALES_PERIODS = {
  "2026-H1": { url: "2026-01-to-06", label: "2026년 1~6월", start: "2026-01-01", end: "2026-06-30" },
  "2026-H2": { url: "2026-07-to-12", label: "2026년 7~12월", start: "2026-07-01", end: "2026-12-31" },
} as const;

export type SalesPeriod = keyof typeof SALES_PERIODS;
export const salesPeriods = Object.keys(SALES_PERIODS) as SalesPeriod[];

export function parseSalesPeriod(value: string | null) {
  return salesPeriods.find(period => value === period || value === SALES_PERIODS[period].url);
}

export function salesPeriodQuery(period: SalesPeriod) {
  return `period=${SALES_PERIODS[period].url}`;
}

export function friendlySalesPeriods(message: string) {
  return salesPeriods.reduce((text, period) => text.replaceAll(period, SALES_PERIODS[period].label), message);
}
