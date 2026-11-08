"""Per-provider budget reservations for the structure experiment.

The book refuses a call whose maximum cost would pass the existing cap.
It does not retry a failed request. Reservations survive so a run can resume.
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


class BudgetStop(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class RunnerStop(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _money(value: Decimal | int | float) -> float:
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(number.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


class ProviderBook:
    def __init__(self, path: Path, provider: str, cap_krw: Decimal, *, external_measured: Decimal = Decimal("0"),
                 external_unsettled: Decimal = Decimal("0"), krw_per_usd: Decimal = Decimal("2200")):
        self.path = path
        self.provider = provider
        self.cap = cap_krw
        self.krw_per_usd = krw_per_usd
        self.external_measured = external_measured
        self.external_unsettled = external_unsettled

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            state = {"provider": self.provider, "entries": []}
        state["provider"] = self.provider
        state["cap_krw"] = _money(self.cap)
        state["external_measured_krw"] = _money(self.external_measured)
        state["external_unsettled_krw"] = _money(self.external_unsettled)
        state["krw_per_usd"] = _money(self.krw_per_usd)
        return state

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def exposure(self, state: dict | None = None) -> Decimal:
        state = state or self.load()
        liability = sum(_decimal(entry.get("liability_krw")) for entry in state.get("entries") or [])
        return self.external_measured + self.external_unsettled + liability

    def remaining(self) -> Decimal:
        return self.cap - self.exposure()

    def maximum_cost(self, input_tokens: int, output_tokens: int, prices_per_1m: dict[str, Decimal]) -> Decimal:
        input_rate = prices_per_1m.get("reservation_input", prices_per_1m["input"])
        return (input_rate * Decimal(input_tokens) + prices_per_1m["output"] * Decimal(output_tokens)) / Decimal(1_000_000) * self.krw_per_usd

    def reserve(self, identity: str, maximum: Decimal, *, detail: dict | None = None) -> dict:
        if maximum <= 0:
            raise BudgetStop("reservation_must_be_positive")
        state = self.load()
        if self.exposure(state) + maximum > self.cap:
            raise BudgetStop("next_call_exceeds_remaining_cap")
        sequence = 1 + sum(1 for entry in state["entries"] if entry.get("identity") == identity)
        entry = {
            "attempt_id": f"{identity}-attempt{sequence}",
            "identity": identity,
            "provider": self.provider,
            "maximum_krw": _money(maximum),
            "liability_krw": _money(maximum),
            "measured_krw": None,
            "status": "reserved",
            "detail": detail or {},
        }
        state["entries"].append(entry)
        self.save(state)
        return entry

    def settle(self, attempt_id: str, measured: Decimal) -> dict:
        state = self.load()
        entry = self._entry(state, attempt_id)
        entry["measured_krw"] = _money(measured)
        entry["liability_krw"] = _money(measured)
        entry["status"] = "settled"
        self.save(state)
        return entry

    def release_before_http(self, attempt_id: str, reason: str) -> dict:
        state = self.load()
        entry = self._entry(state, attempt_id)
        if entry.get("status") != "reserved":
            raise BudgetStop("only_reserved_attempt_can_be_released")
        entry["liability_krw"] = 0
        entry["measured_krw"] = 0
        entry["status"] = "released_before_http"
        entry["reason"] = reason
        self.save(state)
        return entry

    def fail_after_http(self, attempt_id: str, reason: str, *, usage_known: bool, measured: Decimal | None = None) -> dict:
        state = self.load()
        entry = self._entry(state, attempt_id)
        entry["reason"] = reason
        if usage_known and measured is not None:
            entry["measured_krw"] = _money(measured)
            entry["liability_krw"] = _money(measured)
            entry["status"] = "failed_measured"
        else:
            entry["status"] = "failed_unsettled"
        self.save(state)
        return entry

    def resume_open(self) -> list[dict]:
        state = self.load()
        return [entry for entry in state.get("entries") or [] if entry.get("status") in {"reserved", "failed_unsettled"}]

    def snapshot(self) -> dict:
        state = self.load()
        entries = state.get("entries") or []
        measured = sum(_decimal(entry.get("measured_krw")) for entry in entries if entry.get("measured_krw") is not None)
        unsettled = sum(_decimal(entry.get("liability_krw")) for entry in entries if entry.get("measured_krw") is None and _decimal(entry.get("liability_krw")) > 0)
        exposure = self.external_measured + self.external_unsettled + measured + unsettled
        return {
            "provider": self.provider,
            "cap_krw": _money(self.cap),
            "prior_measured_krw": _money(self.external_measured),
            "prior_unsettled_krw": _money(self.external_unsettled),
            "this_run_measured_krw": _money(measured),
            "this_run_unsettled_krw": _money(unsettled),
            "exposure_krw": _money(exposure),
            "remaining_krw": _money(self.cap - exposure),
            "open_attempts": [entry.get("attempt_id") for entry in self.resume_open()],
        }

    def _entry(self, state: dict, attempt_id: str) -> dict:
        for entry in state.get("entries") or []:
            if entry.get("attempt_id") == attempt_id:
                return entry
        raise BudgetStop("unknown_attempt")


def reject_automatic_retry(retry_requested: bool) -> None:
    if retry_requested:
        raise RunnerStop("automatic_paid_retry_forbidden")


def reconcile_prior_exposure(benchmark_root: Path) -> dict[str, dict[str, Decimal]]:
    """Sum earlier ledgers separately for OpenAI and GCP. Does not add a new cap.

    GCP uses the v3 audit exposure plus later Vertex entries and the v2 ledger.
    OpenAI uses the saved Luna low runs, the live ledger, the quality ledger,
    the pilot ledger, and later OpenAI entries in the v4 ledger.
    """
    root = benchmark_root / "모델성능검증"
    openai_measured = Decimal("0")
    openai_unsettled = Decimal("0")
    gcp_measured = Decimal("0")
    gcp_unsettled = Decimal("0")
    notes: list[str] = []

    def add(provider: str, measured: Decimal, unsettled: Decimal, note: str) -> None:
        nonlocal openai_measured, openai_unsettled, gcp_measured, gcp_unsettled
        if provider == "openai":
            openai_measured += measured
            openai_unsettled += unsettled
        else:
            gcp_measured += measured
            gcp_unsettled += unsettled
        notes.append(note)

    v3_path = root / "DocumentAI-pipeline-v3" / "비용원장.json"
    v3 = json.loads(v3_path.read_text(encoding="utf-8"))
    audit = v3.get("audit_summary") or {}
    v3_exposure = _decimal(audit.get("total_exposure_liability_krw"))
    v3_measured = _decimal(audit.get("settled_total_cost_krw"))
    v3_unsettled = _decimal(audit.get("unverified_reserved_liability_krw"))
    if v3_measured + v3_unsettled < v3_exposure:
        v3_unsettled = v3_exposure - v3_measured
    add("gcp", v3_measured, v3_unsettled, "pipeline-v3 audit")

    v2 = json.loads((root / "DocumentAI-pipeline-v2" / "비용원장_세경로.json").read_text(encoding="utf-8"))
    v2_measured = sum((_decimal(entry.get("measured_cost_krw") or entry.get("cost_krw")) for entry in v2.get("entries") or []), Decimal("0"))
    add("gcp", v2_measured, Decimal("0"), "pipeline-v2")

    v4 = json.loads((root / "DocumentAI-pipeline-v4-full" / "ledger.json").read_text(encoding="utf-8"))
    for entry in v4.get("entries") or []:
        model = str(entry.get("model") or "")
        provider = "gcp" if "gemini" in model or entry.get("provider") == "vertex" else "openai" if "gpt" in model or entry.get("provider") == "openai" else ""
        if not provider:
            continue
        measured = entry.get("measured_cost_krw")
        liability = _decimal(entry.get("liability_krw"))
        if measured is None:
            add(provider, Decimal("0"), liability, "pipeline-v4 unsettled")
        else:
            add(provider, _decimal(measured), Decimal("0"), "pipeline-v4 measured")

    live = json.loads((root / "DocumentAI-luna-live-v1" / "live_ledger.json").read_text(encoding="utf-8"))
    live_measured = Decimal("0")
    live_unsettled = Decimal("0")
    for entry in live.get("attempts") or []:
        if entry.get("cost_krw") is not None and entry.get("status") != "reserved":
            live_measured += _decimal(entry.get("cost_krw"))
        elif _decimal(entry.get("reserved_krw")) > 0 and entry.get("status") == "reserved":
            live_unsettled += _decimal(entry.get("reserved_krw"))
    add("openai", live_measured, live_unsettled, "luna-live")

    quality = json.loads((root / "DocumentAI-luna-quality-v1" / "luna_비용원장.json").read_text(encoding="utf-8"))
    add("openai", _decimal((quality.get("summary") or {}).get("settled_cost_krw")), _decimal((quality.get("summary") or {}).get("unverified_reserved_krw")), "luna-quality")

    pilot = json.loads((root / "Luna-low-error-analysis-v1" / "luna_pilot_budget_ledger.json").read_text(encoding="utf-8"))
    for entry in pilot.get("attempts") or []:
        if entry.get("cost_krw") is not None:
            add("openai", _decimal(entry.get("cost_krw")), Decimal("0"), "luna-pilot")
        elif entry.get("status") == "reserved":
            add("openai", Decimal("0"), _decimal(entry.get("reserved_krw")), "luna-pilot reserved")

    optimized = _optimized_luna_exposure(root / "DocumentAI-luna-optimized-v1" / "runs")
    add("openai", optimized, Decimal("0"), "luna-optimized saved usage")
    return {
        "openai": {"measured": openai_measured, "unsettled": openai_unsettled},
        "gcp": {"measured": gcp_measured, "unsettled": gcp_unsettled},
        "notes": notes,
    }


def _usage_cost(usage: dict) -> Decimal:
    details = usage.get("input_tokens_details") or {}
    cached = _decimal(details.get("cached_tokens"))
    write = _decimal(details.get("cache_write_tokens"))
    uncached = max(Decimal("0"), _decimal(usage.get("input_tokens")) - cached - write)
    output = _decimal(usage.get("output_tokens"))
    usd = uncached * Decimal("0.10") + cached * Decimal("0.01") + write * Decimal("0.125") + output * Decimal("0.50")
    return usd / Decimal(1_000_000) * Decimal("2200")


def _find_usage(value: Any) -> dict | None:
    if isinstance(value, dict):
        if "input_tokens" in value and "output_tokens" in value:
            return value
        for child in value.values():
            found = _find_usage(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_usage(child)
            if found:
                return found
    return None


def _optimized_luna_exposure(runs: Path) -> Decimal:
    """Recalculate saved gpt-6-luna usage with the service rate. USD/KRW 2200."""
    total = Decimal("0")
    if not runs.exists():
        return total
    for path in runs.glob("*/*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        usage = _find_usage(record.get("usage")) or _find_usage(record.get("response")) or _find_usage(record)
        if not usage:
            continue
        total += _usage_cost(usage)
    return total


def accept_cached_response(cached: dict | None, identity: str) -> dict | None:
    if not cached:
        return None
    if cached.get("identity") != identity:
        raise RunnerStop("schema_or_prompt_mismatch_cache_rejected")
    if cached.get("response_hash") != cached.get("stored_hash"):
        raise RunnerStop("response_hash_mismatch")
    return cached.get("body")
