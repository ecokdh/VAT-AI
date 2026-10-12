export const periodDefinitions: Record<string, {label:string; start:string; end:string; deadline:string; kind:string}> = {
  "2026-Q1": {label:"2026년 1기 예정", start:"2026-01-01", end:"2026-04-01", deadline:"2026-04-27", kind:"예정신고"},
  "2026-H1": {label:"2026년 1기", start:"2026-01-01", end:"2026-07-01", deadline:"2026-07-27", kind:"확정신고"},
  "2026-Q3": {label:"2026년 2기 예정", start:"2026-07-01", end:"2026-10-01", deadline:"2026-10-26", kind:"예정신고"},
  "2026-H2": {label:"2026년 2기", start:"2026-07-01", end:"2027-01-01", deadline:"2027-01-25", kind:"확정신고"},
  "2026-YEAR": {label:"2026년 연간 신고", start:"2026-01-01", end:"2027-01-01", deadline:"2027-01-25", kind:"연간 신고"},
};

export function availablePeriods(entity: string | null | undefined, taxType: string | null | undefined) {
  if (!entity || !taxType || (entity === "corporation" && taxType === "simplified")) return [];
  if (taxType === "simplified") return ["2026-YEAR"];
  if (taxType !== "general") return [];
  return entity === "corporation" ? ["2026-Q1", "2026-H1", "2026-Q3", "2026-H2"] : ["2026-H1", "2026-H2"];
}

export function choosePeriod(options: string[], requested: string | null, saved: string | null, today = new Date()) {
  if (requested && options.includes(requested)) return requested;
  if (saved && options.includes(saved)) return saved;
  const date = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;
  return options.find(key => periodDefinitions[key].deadline >= date) ?? options.at(-1) ?? "";
}
