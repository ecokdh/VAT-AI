import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getMe, type AuthUser } from "../api/auth";
import { getTaxProfile, type TaxProfileApi } from "../api/transactions";
import { availablePeriods, choosePeriod } from "./filingPeriods";

export function useFilingPeriod() {
  const [params, setParams] = useSearchParams();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<TaxProfileApi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([getMe(), getTaxProfile()]).then(([account, facts]) => {
      if (!active) return;
      setUser(account); setProfile(facts);
      setSaved(sessionStorage.getItem(`vat-ai:filing:${account.id}`));
    }).catch(() => { if(active) setError("사업자정보를 불러오지 못했습니다."); })
      .finally(() => { if(active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const verifiedType = user?.business?.tax_type_code === "01" ? "general" : user?.business?.tax_type_code === "02" ? "simplified" : null;
  const taxType = profile?.tax_type ?? verifiedType;
  const mismatch = !!(profile?.tax_type && verifiedType && profile.tax_type !== verifiedType);
  const options = mismatch ? [] : availablePeriods(profile?.entity_type, taxType);
  const period = choosePeriod(options, params.get("period"), saved);
  useEffect(() => { if(user && period) sessionStorage.setItem(`vat-ai:filing:${user.id}`, period); }, [user, period]);
  function setPeriod(value:string) {
    if (!options.includes(value)) return;
    setSaved(value);
    const next = new URLSearchParams(params); next.set("period",value); setParams(next, {replace:true});
    if(user) sessionStorage.setItem(`vat-ai:filing:${user.id}`, value);
  }
  return {user, profile, taxType, verifiedType, options, period, setPeriod, loading, error,
    blockedReason: mismatch ? "입력한 과세유형과 국세청 조회 결과가 다릅니다. 사업자정보를 확인해 주세요." : ""};
}
