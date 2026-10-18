from datetime import date

import pytest

from ar.aging import (BUCKETS, aging_pivot, bucket, bucket_keys, dso, dunning,
                      open_items, totals_by_currency, unapplied_credits)
from ar.model import Customer, Dataset, Invoice, Payment

AS_OF = date(2026, 6, 30)


@pytest.mark.parametrize("days,expected", [
    (-10, "current"), (0, "current"), (1, "1-30"), (30, "1-30"), (31, "31-60"),
    (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+"), (400, "90+"),
])
def test_bucket_edges(days, expected):
    assert bucket(days) == expected


def inv(id, due, net, tax=0.0, cur="USD", cust="c1", issue=None):
    return Invoice(id=id, customer_id=cust, entity="Inc", issue_date=issue or date(2025, 12, 1),
                   due_date=due, currency=cur, net=net, tax=tax)


def ds_basic():
    return Dataset(
        customers=[Customer("c1", "Acme Logistics", "Inc", "USD"),
                   Customer("c2", "Borealis Freight", "Ltd", "EUR")],
        invoices=[
            inv("A1", date(2026, 7, 15), 1000.0),                    # not due -> current
            inv("A2", date(2026, 6, 10), 2000.0, tax=100.0),         # 20 days -> 1-30
            inv("A3", date(2026, 3, 1), 3000.0),                     # 121 days -> 90+
            inv("A4", date(2026, 5, 1), 500.0),                      # fully paid
            inv("B1", date(2026, 4, 20), 4000.0, cur="EUR", cust="c2"),  # 71 days -> 61-90
            inv("F1", date(2026, 8, 30), 999.0, issue=date(2026, 7, 31)),  # issued after as-of
        ],
        payments=[
            Payment("p1", "c1", date(2026, 6, 1), "USD", 500.0, invoice_id="A4"),
            Payment("p2", "c1", date(2026, 6, 20), "USD", 600.0, invoice_id="A2"),   # partial
            Payment("p3", "c1", date(2026, 6, 25), "USD", 250.0, kind="credit"),     # unapplied
            Payment("p4", "c1", date(2026, 7, 5), "USD", 3000.0, invoice_id="A3"),   # after as-of
        ],
    )


def test_open_items_status_and_balances():
    rows = {r["invoice_id"]: r for r in open_items(ds_basic(), AS_OF)}
    assert "F1" not in rows
    assert rows["A1"]["status"] == "open" and rows["A1"]["bucket"] == "current"
    assert rows["A2"]["open"] == 1500.0 and rows["A2"]["status"] == "overdue"
    assert rows["A2"]["days_overdue"] == 20 and rows["A2"]["bucket"] == "1-30"
    assert rows["A3"]["open"] == 3000.0 and rows["A3"]["bucket"] == "90+"   # later payment ignored
    assert rows["A4"]["status"] == "paid" and rows["A4"]["bucket"] is None


def test_pivot_gross_minus_credits_equals_net():
    ds = ds_basic()
    items = open_items(ds, AS_OF)
    pivot = aging_pivot(items, unapplied_credits(ds, AS_OF))
    usd = next(g for g in pivot if g["customer_id"] == "c1")
    assert usd["current"] == 1000.0 and usd["1-30"] == 1500.0 and usd["90+"] == 3000.0
    assert usd["gross"] == 5500.0
    assert usd["past_due"] == 4500.0
    assert usd["credits"] == 250.0
    assert usd["net"] == 5250.0
    eur = next(g for g in pivot if g["customer_id"] == "c2")
    assert eur["61-90"] == 4000.0 and eur["currency"] == "EUR"
    totals = totals_by_currency(pivot)
    assert set(totals) == {"USD", "EUR"}   # never summed across currencies
    assert totals["USD"]["net"] == 5250.0


def test_overpayment_becomes_credit():
    ds = Dataset(customers=[Customer("c1", "Acme", "Inc", "USD")],
                 invoices=[inv("X", date(2026, 6, 1), 100.0)],
                 payments=[Payment("p", "c1", date(2026, 6, 2), "USD", 130.0, invoice_id="X")])
    rows = open_items(ds, AS_OF)
    assert rows[0]["status"] == "paid" and rows[0]["open"] == 0.0
    assert unapplied_credits(ds, AS_OF) == [{"customer_id": "c1", "currency": "USD", "amount": 30.0}]


def test_dunning_filters_and_sorts():
    ds = ds_basic()
    items = open_items(ds, AS_OF)
    groups = dunning(ds, items, min_days=1)
    assert [g["customer_id"] for g in groups] == ["c1", "c2"]     # 121 days beats 71
    assert groups[0]["total"] == 4500.0 and groups[0]["max_days"] == 121
    assert [r["invoice_id"] for r in groups[0]["invoices"]] == ["A3", "A2"]
    assert [g["customer_id"] for g in dunning(ds, items, min_days=90)] == ["c1"]


def test_dso_converts_fx():
    ds = ds_basic()
    items = open_items(ds, AS_OF)
    # only F1 is excluded (issued after as-of); window of 365 includes the rest (issued 2025-12-01)
    value = dso(ds, items, AS_OF, {"EUR": 1.10}, window_days=365)
    billed = 1000 + 2100 + 3000 + 500 + 4000 * 1.10
    ar = 1000 + 1500 + 3000 + 4000 * 1.10
    assert value == round(ar / billed * 365, 1)


def test_validate_catches_bad_refs():
    ds = ds_basic()
    ds.payments.append(Payment("bad", "c1", AS_OF, "EUR", 1.0, invoice_id="A1"))
    ds.invoices.append(inv("Z", date(2026, 1, 1), 1.0, cust="ghost"))
    errs = ds.validate()
    assert any("currency differs" in e for e in errs)
    assert any("unknown customer ghost" in e for e in errs)
    assert ds_basic().validate() == []


def test_bucket_keys():
    assert bucket_keys() == BUCKETS == ("current", "1-30", "31-60", "61-90", "90+")
    assert bucket_keys([15, 45]) == ("current", "1-15", "16-45", "45+")
    assert bucket_keys([30, 60, 90], "invoice_date") == ("0-30", "31-60", "61-90", "90+")
    assert bucket_keys([7]) == ("current", "1-7", "7+")


@pytest.mark.parametrize("days,bounds,basis,expected", [
    (0, [15, 45], "due_date", "current"), (15, [15, 45], "due_date", "1-15"), (16, [15, 45], "due_date", "16-45"),
    (46, [15, 45], "due_date", "45+"), (0, [30, 60], "invoice_date", "0-30"), (31, [30, 60], "invoice_date", "31-60"),
    (61, [30, 60], "invoice_date", "60+"),
])
def test_bucket_with_rules(days, bounds, basis, expected):
    assert bucket(days, bounds, basis) == expected


def test_grace_days_delay_overdue_but_not_days_count():
    ds = ds_basic()
    rows = {r["invoice_id"]: r for r in open_items(ds, AS_OF, {"grace_days": 25})}
    assert rows["A2"]["days_overdue"] == 20                 # real lateness is still reported
    assert rows["A2"]["status"] == "partial" and rows["A2"]["bucket"] == "current"
    assert rows["A3"]["status"] == "overdue" and rows["A3"]["bucket"] == "90+"   # 121 - 25 = 96
    items = open_items(ds, AS_OF, {"grace_days": 25})
    assert [r["invoice_id"] for g in dunning(ds, items) for r in g["invoices"]] == ["A3", "B1"]


def test_invoice_date_basis_ages_from_issue():
    ds = ds_basic()
    rules = {"basis": "invoice_date", "bucket_boundaries": [30, 60, 90]}
    items = open_items(ds, AS_OF, rules)
    rows = {r["invoice_id"]: r for r in items}
    assert rows["A1"]["bucket"] == "90+"             # issued 2025-12-01, 211 days old, but not yet due
    assert rows["A1"]["status"] == "open"
    pivot = aging_pivot(items, unapplied_credits(ds, AS_OF), bucket_keys([30, 60, 90], "invoice_date"))
    usd = next(g for g in pivot if g["customer_id"] == "c1")
    assert usd["90+"] == 5500.0 and usd["past_due"] == 4500.0   # past due still means overdue by due date
    assert totals_by_currency(pivot, bucket_keys([30, 60, 90], "invoice_date"))["USD"]["0-30"] == 0.0


def test_grace_does_not_shift_bucket_edges():
    ds = Dataset(customers=[Customer("c1", "Acme", "Inc", "USD")],
                 invoices=[inv("L", date(2026, 5, 30), 100.0)])          # 31 days late
    row = open_items(ds, AS_OF, {"grace_days": 3})[0]
    assert row["status"] == "overdue" and row["days_overdue"] == 31 and row["bucket"] == "31-60"
