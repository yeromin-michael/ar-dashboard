from datetime import date

import pytest

from ar.connectors.file import load_mapping, parse_timing
from ar.connectors.sample import load
from ar.model import Customer, Dataset, RevenueLine


@pytest.mark.parametrize("category,expected", [
    ("subscription", "over_time"), ("data", "over_time"),
    ("hardware", "point_in_time"), ("adjustment", "point_in_time"), ("something-new", "point_in_time"),
])
def test_default_timing_from_category(category, expected):
    assert RevenueLine("c", "2026-01", category, 1.0, "USD").timing == expected


def test_explicit_timing_overrides_category():
    assert RevenueLine("c", "2026-01", "hardware", 1.0, "USD", timing="over_time").timing == "over_time"


def test_validation_rejects_unknown_timing():
    ds = Dataset(customers=[Customer("c", "C", "Inc", "USD")],
                 revenue=[RevenueLine("c", "2026-01", "data", 1.0, "USD", timing="whenever")])
    assert any("unknown revenue type" in e for e in ds.validate())


@pytest.mark.parametrize("raw,expected", [
    ("Over time", "over_time"), ("over-time", "over_time"), ("Ratably", "over_time"),
    ("Point in time", "point_in_time"), ("At a point in time", "point_in_time"), ("PIT", "point_in_time"),
    ("", ""), (None, ""),
])
def test_parse_timing(raw, expected):
    assert parse_timing(raw) == expected


def test_parse_timing_rejects_unknown():
    with pytest.raises(ValueError):
        parse_timing("sometimes")


def test_file_revenue_with_timing_column(tmp_path):
    (tmp_path / "inv.csv").write_text("Doc,Client,Date,Total\nA-1,X,2026-05-01,100\n")
    (tmp_path / "rev.csv").write_text("Client,Month,Category,Amount,Type\nX,2026-05,hardware,100,Over time\nX,2026-05,data,50,\n")
    ds = load_mapping({"files": {
        "invoices": {"path": "inv.csv", "columns": {"id": "Doc", "customer_name": "Client", "issue_date": "Date", "total": "Total"}},
        "revenue": {"path": "rev.csv", "columns": {"customer_name": "Client", "month": "Month", "category": "Category",
                                                   "amount": "Amount", "timing": "Type"}}}}, tmp_path)
    assert [r.timing for r in ds.revenue] == ["over_time", "over_time"]   # explicit override, then data default
    assert ds.validate() == []


def test_sample_has_both_revenue_types():
    ds = load({"seed": 7}, date(2026, 6, 30))
    assert {r.timing for r in ds.revenue} == {"over_time", "point_in_time"}
