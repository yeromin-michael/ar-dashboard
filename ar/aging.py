"""Aging and AR metrics, computed from a Dataset as of a given date.

Nothing here is stored on the records: days overdue, buckets and balances
are always derived from due dates, payments and the as-of date.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .model import Dataset, Invoice

DEFAULT_BOUNDARIES = (30, 60, 90)
EPS = 0.005


def bucket_keys(boundaries=DEFAULT_BOUNDARIES, basis: str = "due_date") -> tuple[str, ...]:
    """Bucket names. Due-date aging starts with "current" (not yet due); invoice-date
    aging counts days since issue, so the first bucket is "0-N"."""
    b = list(boundaries)
    first = ("current", f"1-{b[0]}") if basis == "due_date" else (f"0-{b[0]}",)
    return first + tuple(f"{lo + 1}-{hi}" for lo, hi in zip(b, b[1:])) + (f"{b[-1]}+",)


BUCKETS = bucket_keys()
PAST_DUE = BUCKETS[1:]


def bucket(days: int, boundaries=DEFAULT_BOUNDARIES, basis: str = "due_date") -> str:
    """Due-date basis: days past due, 0 or less is current. Invoice-date basis: days since issue."""
    keys = bucket_keys(boundaries, basis)
    if basis == "due_date":
        if days <= 0:
            return keys[0]
        keys = keys[1:]
    for key, hi in zip(keys, boundaries):
        if days <= hi:
            return key
    return keys[-1]


def _r(x: float) -> float:
    return round(x + 0.0, 2)


def open_items(ds: Dataset, as_of: date, rules: dict | None = None) -> list[dict]:
    """One row per invoice issued on/before as_of, with paid/open/aging.

    rules = the profile's "aging" section: bucket_boundaries, basis (due_date |
    invoice_date) and grace_days. An invoice inside its grace period is not
    overdue yet. days_overdue always reports the real days past the due date.
    """
    rules = rules or {}
    bounds = rules.get("bucket_boundaries", DEFAULT_BOUNDARIES)
    basis = rules.get("basis", "due_date")
    grace = rules.get("grace_days", 0)
    applied: dict[str, float] = defaultdict(float)
    for p in ds.payments:
        if p.invoice_id and p.date <= as_of:
            applied[p.invoice_id] += p.amount
    rows = []
    for inv in ds.invoices:
        if inv.issue_date > as_of:
            continue
        paid = _r(min(applied[inv.id], inv.total))
        open_amt = _r(inv.total - paid)
        days = (as_of - inv.due_date).days
        late = days - grace
        if open_amt <= EPS:
            status = "paid"
        elif late > 0:
            status = "overdue"
        elif paid > EPS:
            status = "partial"
        else:
            status = "open"
        rows.append({
            "invoice_id": inv.id,
            "customer_id": inv.customer_id,
            "currency": inv.currency,
            "total": inv.total,
            "paid": paid,
            "open": max(open_amt, 0.0),
            "days_overdue": max(days, 0),
            # within grace stays current; once overdue, the bucket uses the real days late
            "bucket": (bucket((days if late > 0 else 0) if basis == "due_date" else (as_of - inv.issue_date).days,
                              bounds, basis)
                       if open_amt > EPS else None),
            "status": status,
        })
    return rows


def unapplied_credits(ds: Dataset, as_of: date) -> list[dict]:
    """Payments/credits not tied to an invoice, plus overpayments, per customer+currency."""
    totals: dict[tuple, float] = defaultdict(float)
    for p in ds.payments:
        if p.date <= as_of and not p.invoice_id:
            totals[(p.customer_id, p.currency)] += p.amount
    applied: dict[str, float] = defaultdict(float)
    for p in ds.payments:
        if p.invoice_id and p.date <= as_of:
            applied[p.invoice_id] += p.amount
    for inv in ds.invoices:
        over = applied[inv.id] - inv.total
        if inv.issue_date <= as_of and over > EPS:
            totals[(inv.customer_id, inv.currency)] += over
    return [{"customer_id": c, "currency": cur, "amount": _r(a)}
            for (c, cur), a in sorted(totals.items()) if a > EPS]


def aging_pivot(items: list[dict], credits: list[dict], buckets=BUCKETS) -> list[dict]:
    """Rows of customer x currency with bucket totals, past due, credits and net.
    Past due = open amount of overdue invoices, so it holds on any aging basis."""
    groups: dict[tuple, dict] = {}

    def row(cid: str, cur: str) -> dict:
        key = (cid, cur)
        if key not in groups:
            groups[key] = {"customer_id": cid, "currency": cur,
                           **{b: 0.0 for b in buckets}, "credits": 0.0, "past_due": 0.0}
        return groups[key]

    for it in items:
        if it["open"] > EPS:
            g = row(it["customer_id"], it["currency"])
            g[it["bucket"]] += it["open"]
            if it["status"] == "overdue":
                g["past_due"] += it["open"]
    for cr in credits:
        row(cr["customer_id"], cr["currency"])["credits"] += cr["amount"]
    out = []
    for g in groups.values():
        for b in buckets:
            g[b] = _r(g[b])
        g["credits"] = _r(g["credits"])
        g["gross"] = _r(sum(g[b] for b in buckets))
        g["past_due"] = _r(g.pop("past_due"))
        g["net"] = _r(g["gross"] - g["credits"])
        out.append(g)
    return sorted(out, key=lambda g: (g["currency"], -g["gross"], g["customer_id"]))


def totals_by_currency(pivot: list[dict], buckets=BUCKETS) -> dict[str, dict]:
    keys = tuple(buckets) + ("gross", "past_due", "credits", "net")
    out: dict[str, dict] = {}
    for g in pivot:
        t = out.setdefault(g["currency"], {k: 0.0 for k in keys})
        for k in keys:
            t[k] += g[k]
    return {cur: {k: _r(v) for k, v in t.items()} for cur, t in out.items()}


def to_usd(amount: float, currency: str, fx_to_usd: dict[str, float]) -> float:
    if currency == "USD":
        return amount
    if currency not in fx_to_usd:
        raise KeyError(f"no FX rate for {currency}")
    return _r(amount * fx_to_usd[currency])


def dso(ds: Dataset, items: list[dict], as_of: date, fx_to_usd: dict[str, float], window_days: int = 90) -> float | None:
    """Simple DSO: open AR / revenue invoiced in the window * window, in USD."""
    start = as_of - timedelta(days=window_days)
    billed = sum(to_usd(i.total, i.currency, fx_to_usd)
                 for i in ds.invoices if start < i.issue_date <= as_of)
    if billed <= EPS:
        return None
    ar = sum(to_usd(it["open"], it["currency"], fx_to_usd) for it in items)
    return round(ar / billed * window_days, 1)


def dunning(ds: Dataset, items: list[dict], min_days: int = 1) -> list[dict]:
    """Overdue invoices grouped by customer+currency, worst first."""
    by_id: dict[str, Invoice] = {i.id: i for i in ds.invoices}
    groups: dict[tuple, dict] = {}
    for it in items:
        if it["status"] == "overdue" and it["days_overdue"] >= min_days:
            key = (it["customer_id"], it["currency"])
            g = groups.setdefault(key, {"customer_id": key[0], "currency": key[1],
                                        "invoices": [], "total": 0.0, "max_days": 0})
            g["invoices"].append({"invoice_id": it["invoice_id"],
                                  "due_date": by_id[it["invoice_id"]].due_date.isoformat(),
                                  "open": it["open"], "days_overdue": it["days_overdue"]})
            g["total"] += it["open"]
            g["max_days"] = max(g["max_days"], it["days_overdue"])
    out = list(groups.values())
    for g in out:
        g["total"] = _r(g["total"])
        g["invoices"].sort(key=lambda r: r["due_date"])
    return sorted(out, key=lambda g: (-g["max_days"], -g["total"]))
