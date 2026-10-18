"""Company profile: how one company's AR works (entities, revenue streams, terms, aging policy).

Filled in by the onboarding form and reviewed before real data is loaded. A real
profile is client-confidential and lives in data/private/; only fictional examples
are committed. A missing profile, or a missing section, falls back to DEFAULTS,
which reproduce the dashboard's built-in behavior.
"""
from __future__ import annotations

import calendar
import copy
import json
import re
from datetime import date, timedelta
from pathlib import Path

PROFILE_VERSION = 1
REVENUE_TYPES = ("over_time", "point_in_time")
BILLING_MODELS = ("upfront", "monthly", "quarterly", "annual", "usage", "milestone", "one_off")
AGING_BASES = ("due_date", "invoice_date")
TERMS_BASES = ("net", "eom")       # eom = days counted from the end of the invoice month
MODULES = ("revenue_recognition", "dunning", "whats_next", "usage_billing", "serials")
MAX_BUCKET_BOUNDARIES = 5    # + "current" = 7 buckets, one per color in the --b0..--b6 ramp

DEFAULTS: dict = {
    "profile_version": PROFILE_VERSION,
    "company": {"name": "", "reporting_currency": "USD", "fiscal_year_start_month": 1},
    "currencies": ["USD", "EUR", "ILS"],
    "entities": [],                 # empty = accept any entity found in the data
    "revenue_streams": [
        {"key": "subscription", "label": "Subscription", "revenue_type": "over_time", "billing_model": "monthly"},
        {"key": "data", "label": "Data", "revenue_type": "over_time", "billing_model": "monthly"},
        {"key": "hardware", "label": "Hardware", "revenue_type": "point_in_time", "billing_model": "one_off"},
        {"key": "adjustment", "label": "Adjustment", "revenue_type": "point_in_time", "billing_model": "one_off"},
    ],
    "payment_terms": {"default_days": 30, "basis": "net"},
    "aging": {"bucket_boundaries": [30, 60, 90], "basis": "due_date", "grace_days": 0},
    "collections": {"reminder_thresholds_days": [1, 30, 60, 90], "escalate_after_days": 90,
                    "sender_name": "Accounts Receivable"},
    "modules": {m: True for m in MODULES},
    "targets": {"dso_days": None, "past_due_pct": None},
    "data_source": {"system": "", "mapping": ""},
}

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_CUR = re.compile(r"^[A-Z]{3}$")


def due_date(issue: date, days: int, basis: str = "net") -> date:
    """Due date from payment terms: net = issue + days; eom = end of the issue month + days."""
    if basis == "eom":
        issue = issue.replace(day=calendar.monthrange(issue.year, issue.month)[1])
    return issue + timedelta(days=days)


def timing_by_category(p: dict) -> dict[str, str]:
    return {s["key"]: s["revenue_type"] for s in p["revenue_streams"]}


class ProfileError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("invalid profile:\n  " + "\n  ".join(errors))
        self.errors = errors


def merge(partial: dict) -> dict:
    """DEFAULTS overlaid with a partial profile. Object sections merge key by key; lists replace."""
    out = copy.deepcopy(DEFAULTS)
    for k, v in partial.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(copy.deepcopy(v))
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path: str | Path | None) -> dict:
    """Load, merge with defaults and validate. None -> defaults. Raises ProfileError."""
    if not path:
        return copy.deepcopy(DEFAULTS)
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProfileError([f"{p}: file not found"]) from None
    except json.JSONDecodeError as e:
        raise ProfileError([f"{p}: not valid JSON ({e.msg}, line {e.lineno})"]) from None
    if not isinstance(raw, dict):
        raise ProfileError([f"{p}: must be a JSON object"])
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}   # "_comment" etc.
    prof = merge(raw)
    errors = validate(prof)
    if errors:
        raise ProfileError(errors)
    return prof


def _num(v, lo: float, hi: float, integer: bool = True) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if integer and not isinstance(v, int):
        return False
    return lo <= v <= hi


def _increasing(vals, lo: int, hi: int) -> bool:
    return (isinstance(vals, list) and bool(vals) and all(_num(v, lo, hi) for v in vals)
            and all(a < b for a, b in zip(vals, vals[1:])))


def validate(p: dict) -> list[str]:
    """Problems in a merged profile, each prefixed with the field path (empty = valid)."""
    errs: list[str] = []

    def unknown(section: str, obj: dict, allowed) -> None:
        for k in obj:
            if k not in allowed:
                errs.append(f"{section}.{k}: unknown field")

    unknown("profile", p, DEFAULTS)
    for k, v in DEFAULTS.items():
        if k in p and type(p[k]) is not type(v) and k != "profile_version":
            errs.append(f"{k}: must be {'an object' if isinstance(v, dict) else 'a list'}")
    if errs:
        return errs
    for k, v in DEFAULTS.items():
        if isinstance(v, dict):
            unknown(k, p[k], v)

    if p["profile_version"] != PROFILE_VERSION:
        errs.append(f"profile_version: must be {PROFILE_VERSION}")

    curs = p["currencies"]
    if not curs or not all(isinstance(c, str) and _CUR.match(c) for c in curs):
        errs.append("currencies: list of 3-letter codes such as USD, EUR, ILS")
    elif len(set(curs)) != len(curs):
        errs.append("currencies: duplicates")

    co = p["company"]
    if not isinstance(co["name"], str):
        errs.append("company.name: must be text")
    if co["reporting_currency"] not in curs:
        errs.append(f"company.reporting_currency: {co['reporting_currency']!r} is not in currencies")
    if not _num(co["fiscal_year_start_month"], 1, 12):
        errs.append("company.fiscal_year_start_month: 1-12")

    seen: set = set()
    for i, e in enumerate(p["entities"]):
        where = f"entities[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{where}: must be an object")
            continue
        unknown(where, e, ("code", "name", "currency"))
        code = e.get("code")
        if not isinstance(code, str) or not code.strip():
            errs.append(f"{where}.code: required")
        elif code in seen:
            errs.append(f"{where}.code: duplicate {code!r}")
        seen.add(code)
        if e.get("currency") not in curs:
            errs.append(f"{where}.currency: {e.get('currency')!r} is not in currencies")

    seen = set()
    if not p["revenue_streams"]:
        errs.append("revenue_streams: at least one is required")
    for i, s in enumerate(p["revenue_streams"]):
        where = f"revenue_streams[{i}]"
        if not isinstance(s, dict):
            errs.append(f"{where}: must be an object")
            continue
        unknown(where, s, ("key", "label", "revenue_type", "billing_model"))
        key = s.get("key")
        if not isinstance(key, str) or not _KEY.match(key):
            errs.append(f"{where}.key: lowercase letters, digits and _ (e.g. 'subscription')")
        elif key in seen:
            errs.append(f"{where}.key: duplicate {key!r}")
        seen.add(key)
        if not isinstance(s.get("label"), str) or not s.get("label", "").strip():
            errs.append(f"{where}.label: required")
        if s.get("revenue_type") not in REVENUE_TYPES:
            errs.append(f"{where}.revenue_type: one of {', '.join(REVENUE_TYPES)}")
        if s.get("billing_model") not in BILLING_MODELS:
            errs.append(f"{where}.billing_model: one of {', '.join(BILLING_MODELS)}")

    t = p["payment_terms"]
    if not _num(t["default_days"], 0, 365):
        errs.append("payment_terms.default_days: whole number of days, 0-365")
    if t["basis"] not in TERMS_BASES:
        errs.append(f"payment_terms.basis: one of {', '.join(TERMS_BASES)}")

    a = p["aging"]
    if not _increasing(a["bucket_boundaries"], 1, 3650) or len(a["bucket_boundaries"]) > MAX_BUCKET_BOUNDARIES:
        errs.append(f"aging.bucket_boundaries: 1-{MAX_BUCKET_BOUNDARIES} increasing day counts, e.g. [30, 60, 90]")
    if a["basis"] not in AGING_BASES:
        errs.append(f"aging.basis: one of {', '.join(AGING_BASES)}")
    if not _num(a["grace_days"], 0, 60):
        errs.append("aging.grace_days: whole number of days, 0-60")

    c = p["collections"]
    if not _increasing(c["reminder_thresholds_days"], 1, 3650):
        errs.append("collections.reminder_thresholds_days: increasing day counts, e.g. [1, 30, 60, 90]")
    if not _num(c["escalate_after_days"], 1, 3650):
        errs.append("collections.escalate_after_days: whole number of days, 1-3650")
    if not isinstance(c["sender_name"], str) or not c["sender_name"].strip():
        errs.append("collections.sender_name: required")

    for k, v in p["modules"].items():
        if not isinstance(v, bool):
            errs.append(f"modules.{k}: true or false")

    tg = p["targets"]
    if tg["dso_days"] is not None and not _num(tg["dso_days"], 1, 365, integer=False):
        errs.append("targets.dso_days: 1-365 days, or null")
    if tg["past_due_pct"] is not None and not _num(tg["past_due_pct"], 0, 100, integer=False):
        errs.append("targets.past_due_pct: 0-100, or null")

    for k in ("system", "mapping"):
        if not isinstance(p["data_source"][k], str):
            errs.append(f"data_source.{k}: must be text")
    return errs
