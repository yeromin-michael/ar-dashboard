from datetime import date

import pytest

from ar.aging import (aging_pivot, bucket, dso, dunning, open_items,
                      totals_by_currency, unapplied_credits)
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
