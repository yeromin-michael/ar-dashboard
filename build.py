#!/usr/bin/env python3
"""connector -> validate -> compute -> dist/data.json (+ copy web/ into dist/).

Usage: python3 build.py [--config config.json] [--profile path.json] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from ar import aging, profile
from ar.connectors.base import get
from ar.model import Dataset, to_jsonable

ROOT = Path(__file__).resolve().parent


def resolve_as_of(value: str | None) -> date:
    if not value or value == "today":
        return date.today()
    return date.fromisoformat(value)


def compute(ds: Dataset, as_of: date, fx: dict[str, float]) -> dict:
    items = aging.open_items(ds, as_of)
    credits = aging.unapplied_credits(ds, as_of)
    pivot = aging.aging_pivot(items, credits)
    by_inv = {i.id: i for i in ds.invoices}
    item_by_inv = {it["invoice_id"]: it for it in items}

    recognized: dict[str, float] = defaultdict(float)
    for r in ds.revenue:
        if r.invoice_id and r.month <= as_of.strftime("%Y-%m"):
            recognized[r.invoice_id] += r.amount

    invoices = []
    for inv in ds.invoices:
        it = item_by_inv.get(inv.id)
        if it is None:          # issued after as-of
            continue
        invoices.append({**to_jsonable(inv), "total": inv.total, **it,
                         "month": inv.issue_date.strftime("%Y-%m"),
                         "recognized": round(recognized[inv.id], 2)})

    collections = []
    for p in ds.payments:
        if p.date > as_of or p.kind != "payment":
            continue
        inv = by_inv.get(p.invoice_id) if p.invoice_id else None
        tax_share = (inv.tax / inv.total) if inv and inv.total else 0.0
        collections.append({
            "payment_id": p.id, "customer_id": p.customer_id, "date": p.date.isoformat(),
            "currency": p.currency, "amount": p.amount,
            "tax": round(p.amount * tax_share, 2), "net": round(p.amount * (1 - tax_share), 2),
            "invoice_id": p.invoice_id, "invoice_date": inv.issue_date.isoformat() if inv else None,
            "category": inv.category if inv else "unapplied",
            "entity": inv.entity if inv else next(c.entity for c in ds.customers if c.id == p.customer_id),
            "reference": p.reference,
        })

    usage = [{**to_jsonable(u), "subtotal": u.subtotal, "tax": u.tax, "total": u.total,
              "hw_revenue": round(u.subtotal * u.hw_share, 2),
              "sw_revenue": round(u.subtotal * (1 - u.hw_share), 2)} for u in ds.usage]

    return {
        "meta": {
            "as_of": as_of.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": ds.source,
            "version": (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "dev",
            "fx_to_usd": fx,
            "buckets": list(aging.BUCKETS),
        },
        "kpis": {
            "totals_by_currency": aging.totals_by_currency(pivot),
            "dso_days": aging.dso(ds, items, as_of, fx),
            "open_invoices": sum(1 for it in items if it["open"] > aging.EPS),
            "overdue_invoices": sum(1 for it in items if it["status"] == "overdue"),
        },
        "customers": to_jsonable(ds.customers),
        "invoices": invoices,
        "credits": credits,
        "aging": pivot,
        "dunning": aging.dunning(ds, items, min_days=1),
        "collections": sorted(collections, key=lambda c: c["date"], reverse=True),
        "payments": [to_jsonable(p) for p in ds.payments if p.date <= as_of],
        "revenue": [r for r in to_jsonable(ds.revenue) if r["month"] <= as_of.strftime("%Y-%m")],
        "contracts": to_jsonable(ds.contracts),
        "usage": usage,
        "actions": to_jsonable(ds.actions),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--profile", help="company profile JSON (overrides config.json \"profile\")")
    ap.add_argument("--as-of")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    prof_path = args.profile or cfg.get("profile")
    if prof_path and not Path(prof_path).is_absolute():
        prof_path = ROOT / prof_path
    try:
        prof = profile.load(prof_path)
    except profile.ProfileError as e:
        print(e, file=sys.stderr)
        return 1
    as_of = resolve_as_of(args.as_of or cfg.get("as_of"))
    name = cfg.get("connector", "sample")
    ds = get(name)(cfg.get("options", {}).get(name, {}), as_of)

    errors = ds.validate()
    if errors:
        print("validation failed:\n  " + "\n  ".join(errors[:50]), file=sys.stderr)
        return 1

    data = compute(ds, as_of, cfg.get("fx_to_usd", {}))
    out = Path(args.out)
    if (ROOT / "web").exists():
        shutil.copytree(ROOT / "web", out, dirs_exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    k = data["kpis"]
    print(f"built {out/'data.json'}: {len(data['customers'])} customers, "
          f"{len(data['invoices'])} invoices, {k['open_invoices']} open, "
          f"{k['overdue_invoices']} overdue, DSO {k['dso_days']} (as of {as_of}, source: {ds.source}, "
          f"profile: {Path(prof_path).name if prof_path else 'defaults'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
