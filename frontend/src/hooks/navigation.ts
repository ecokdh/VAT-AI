// Back follows the product hierarchy even after direct links or browser refreshes.
export function parentRoute(pathname: string, search = "") {
  const params = new URLSearchParams(search);
  const period = params.get("period");
  const suffix = period ? `?period=${encodeURIComponent(period)}` : "";
  if (["/signup", "/forgot-password", "/reset-password"].includes(pathname)) return "/login";
  if (params.get("from") === "reports") return `/reports${suffix}`;
  if (pathname === "/storage/trash" || pathname === "/capture" || pathname.startsWith("/receipts/")) {
    return `/storage/${params.get("direction") === "sales" ? "sales" : "purchase"}${suffix}`;
  }
  if (pathname.startsWith("/analysis/")) return `/storage/purchase${suffix}`;
  if (/^\/storage\/(purchase|sales)\/receipts$/.test(pathname)) return `${pathname.replace(/\/receipts$/, "")}${suffix}`;
  return `/dashboard${suffix}`;
}
