import json
from datetime import date

from ar.aging import open_items
from ar.connectors.sample import load
from build import compute

AS_OF = date(2026, 6, 30)


def test_sample_is_valid_and_deterministic():
    a, b = load({"seed": 7}, AS_OF), load({"seed": 7}, AS_OF)
    assert a.validate() == []
    assert json.dumps(compute(a, AS_OF, {"EUR": 1.08, "ILS": 0.27}) | {"meta": None}) == \
        json.dumps(compute(b, AS_OF, {"EUR": 1.08, "ILS": 0.27}) | {"meta": None})


def test_sample_has_every_scenario():
    ds = load({"seed": 7}, AS_OF)
    items = open_items(ds, AS_OF)
    buckets = {it["bucket"] for it in items if it["open"] > 0}
    assert {"current", "1-30", "90+"} <= buckets
    assert {c.currency for c in ds.customers} == {"USD", "EUR", "ILS"}
    assert any(p.invoice_id is None for p in ds.payments)          # unapplied cash / credits
    assert any(i.kind == "deferred" for i in ds.invoices)
    assert ds.usage and any("serials" in c.modules for c in ds.customers)
    assert {a.kind for a in ds.actions} == {"action", "digest"}


def test_nothing_after_as_of():
    ds = load({"seed": 7}, AS_OF)
    assert all(i.issue_date <= AS_OF for i in ds.invoices)
    assert all(p.date <= AS_OF for p in ds.payments)


def test_usage_batches_match_invoices():
    ds = load({"seed": 7}, AS_OF)
    for b in ds.usage:
        billed = [i for i in ds.invoices if i.customer_id == b.customer_id and i.category == "subscription"
                  and i.issue_date.strftime("%Y-%m") == b.month]
        assert len(billed) == 1 and billed[0].net == b.subtotal


def test_whats_next_figures_match_the_data():
    from ar.aging import dunning
    ds = load({"seed": 7}, AS_OF)
    groups = {g["customer_id"]: g for g in dunning(ds, open_items(ds, AS_OF))}
    by_tag = {a.tag: a for a in ds.actions}
    assert len({a.id for a in ds.actions}) == len(ds.actions)          # stable, unique ids
    esc = by_tag["Escalation"]
    g = groups[esc.customer_id]
    assert g["max_days"] >= 60 and f"{g['total']:,.0f}" in esc.title and f"{g['max_days']} days" in esc.body
    cash = by_tag.get("Cash application")
    if cash:
        unapplied = [p for p in ds.payments if p.customer_id == cash.customer_id and p.invoice_id is None and p.kind == "payment"]
        assert any(f"{p.amount:,.0f}" in cash.title for p in unapplied) and cash.customer_id in groups
    assert {a.kind for a in ds.actions} == {"action", "digest"}


def test_whats_next_renewal_handles_leap_day():
    from ar.model import Invoice
    ds = load({"seed": 7}, date(2027, 1, 15))
    ds.invoices.append(Invoice("LEAP", ds.customers[0].id, "Inc", date(2028, 2, 29), date(2028, 3, 30), "USD", 1.0, kind="deferred"))
    ds.actions.clear()
    from ar.connectors.sample import _actions
    import random
    _actions(ds, date(2028, 12, 1), random.Random(1))                 # must not raise on 29 Feb + 1 year
