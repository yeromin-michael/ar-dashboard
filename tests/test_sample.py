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
