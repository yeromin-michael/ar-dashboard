import json
from datetime import date
from pathlib import Path

import pytest

from ar.aging import open_items, unapplied_credits
from ar.connectors.file import MappingError, load_mapping, parse_amount, parse_date

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "erp_export"
AS_OF = date(2026, 6, 30)


def spec():
    return json.loads((ROOT / "mappings" / "example.json").read_text())


@pytest.mark.parametrize("raw,expected", [
    ("1,000.00", 1000.0), ("$1,234.56", 1234.56), ("4.000,00", 4000.0), ("12,5", 12.5),
    ("(1,000.00)", -1000.0), ("-5,000.00", -5000.0), (300, 300.0), ("", 0.0), ("€ 2.331,00", 2331.0),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_date_formats_and_excel_serial():
    assert parse_date("31/03/2026", ["%d/%m/%Y"]) == date(2026, 3, 31)
    assert parse_date(46112, []) == date(2026, 3, 31)
    with pytest.raises(ValueError):
        parse_date("2026.31.03", ["%d/%m/%Y"])


def test_example_mapping_loads_fixture():
    ds = load_mapping(spec(), FIX)
    assert ds.validate() == []
    assert [c.id for c in ds.customers] == ["C001", "C002"]
    assert ds.customers[0].contact_emails == ["alex@harbor.example", "ap@harbor.example"]
    inv = {i.id: i for i in ds.invoices}
    assert inv["INV-2"].currency == "USD" and inv["INV-2"].net == 2500.5
    assert inv["INV-3"].net == 4000.0 and inv["INV-3"].total == 4680.0 and inv["INV-3"].kind == "deferred"
    assert inv["INV-3"].due_date == date(2026, 5, 15)            # derived from 30-day default
    pays = {p.id: p for p in ds.payments}
    assert pays["R-1"].customer_id == "C001" and pays["R-1"].currency == "USD"
    assert pays["R-2"].currency == "EUR"
    assert pays["R-3"].invoice_id is None and pays["R-3"].kind == "credit"
    assert len(ds.revenue) == 3                                    # derived from invoices


def test_aging_on_fixture():
    ds = load_mapping(spec(), FIX)
    rows = {r["invoice_id"]: r for r in open_items(ds, AS_OF)}
    assert rows["INV-1"]["status"] == "paid"
    assert rows["INV-2"]["bucket"] == "1-30" and rows["INV-2"]["open"] == 2500.5
    assert unapplied_credits(ds, AS_OF) == [{"customer_id": "C001", "currency": "USD", "amount": 300.0}]


def test_customers_derived_when_no_customer_file(tmp_path):
    (tmp_path / "ar.csv").write_text("Doc,Client,Date,Total\nA-1,Northside Clinic,2026-05-01,\"1,200\"\n")
    ds = load_mapping({"files": {"invoices": {"path": "ar.csv", "columns": {
        "id": "Doc", "customer_name": "Client", "issue_date": "Date", "total": "Total"}}}}, tmp_path)
    assert ds.validate() == []
    assert ds.customers[0].id == "northside-clinic" and ds.customers[0].name == "Northside Clinic"
    assert ds.invoices[0].total == 1200.0 and ds.invoices[0].due_date == date(2026, 5, 31)


def test_errors_name_file_row_and_field(tmp_path):
    (tmp_path / "ar.csv").write_text("Doc,Client,Date,Total\nA-1,X,2026-05-01,10\nA-2,Y,,20\n")
    with pytest.raises(MappingError, match=r"invoices row 3: .*issue_date"):
        load_mapping({"files": {"invoices": {"path": "ar.csv", "columns": {
            "id": "Doc", "customer_name": "Client", "issue_date": "Date", "total": "Total"}}}}, tmp_path)


def test_xlsx_with_title_rows(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Open invoices report"])                  # title row above the header
    ws.append([])
    ws.append(["Invoice", "Customer", "Invoice date", "Amount"])
    ws.append(["X-1", "Lakeview Partners", date(2026, 4, 1), 950.0])
    wb.save(tmp_path / "open.xlsx")
    ds = load_mapping({"files": {"invoices": {"path": "open.xlsx", "columns": {
        "id": "Invoice", "customer_name": "Customer", "issue_date": "Invoice date", "total": "Amount"}}}}, tmp_path)
    assert ds.invoices[0].issue_date == date(2026, 4, 1) and ds.invoices[0].total == 950.0


def test_negative_receipts_rejected_unless_negated(tmp_path):
    (tmp_path / "inv.csv").write_text("Doc,Client,Date,Total\nA-1,X,2026-05-01,100\n")
    (tmp_path / "pay.csv").write_text("Doc,Date,Amount\nA-1,2026-05-10,(100)\n")
    files = {"invoices": {"path": "inv.csv", "columns": {"id": "Doc", "customer_name": "Client", "issue_date": "Date", "total": "Total"}},
             "payments": {"path": "pay.csv", "columns": {"invoice_id": "Doc", "date": "Date", "amount": "Amount"}}}
    assert any("must be positive" in e for e in load_mapping({"files": files}, tmp_path).validate())
    files["payments"]["negate"] = True
    ds = load_mapping({"files": files}, tmp_path)
    assert ds.validate() == [] and open_items(ds, AS_OF)[0]["status"] == "paid"
