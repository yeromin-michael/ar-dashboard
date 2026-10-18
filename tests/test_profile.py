import json
from datetime import date
from pathlib import Path

import pytest

import build
from ar import aging, model, profile

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "profiles" / "example.json"


def write(tmp_path, obj) -> Path:
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
    return p


def errors_for(tmp_path, partial) -> list[str]:
    with pytest.raises(profile.ProfileError) as e:
        profile.load(write(tmp_path, partial))
    return e.value.errors


def test_defaults_are_valid():
    assert profile.validate(profile.load(None)) == []


def test_defaults_match_built_in_behavior():
    d = profile.DEFAULTS
    assert {s["key"]: s["revenue_type"] for s in d["revenue_streams"]} == model.TIMING_BY_CATEGORY
    assert tuple(d["currencies"]) == model.CURRENCIES
    assert [aging.bucket(b) for b in d["aging"]["bucket_boundaries"]] == list(aging.BUCKETS[1:-1])
    assert aging.bucket(d["aging"]["bucket_boundaries"][-1] + 1) == aging.BUCKETS[-1]
    assert d["aging"]["basis"] == "due_date" and d["aging"]["grace_days"] == 0


def test_example_is_valid():
    p = profile.load(EXAMPLE)
    assert p["company"]["name"].endswith("(fictional)")
    assert [e["code"] for e in p["entities"]] == ["Inc", "Ltd"]


def test_partial_profile_is_filled_from_defaults(tmp_path):
    p = profile.load(write(tmp_path, {"company": {"name": "X"}, "aging": {"grace_days": 5}}))
    assert p["company"] == {"name": "X", "reporting_currency": "USD", "fiscal_year_start_month": 1}
    assert p["aging"]["bucket_boundaries"] == [30, 60, 90] and p["aging"]["grace_days"] == 5
    assert p["revenue_streams"] == profile.DEFAULTS["revenue_streams"]


def test_lists_replace_rather_than_merge(tmp_path):
    p = profile.load(write(tmp_path, {"revenue_streams": [
        {"key": "saas", "label": "SaaS", "revenue_type": "over_time", "billing_model": "annual"}]}))
    assert [s["key"] for s in p["revenue_streams"]] == ["saas"]


def test_comment_keys_are_ignored(tmp_path):
    assert profile.load(write(tmp_path, {"_comment": "hi", "_note": 1})) == profile.load(None)


def test_load_does_not_mutate_defaults(tmp_path):
    before = json.dumps(profile.DEFAULTS)
    profile.load(write(tmp_path, {"aging": {"grace_days": 3}, "modules": {"serials": False}}))
    assert json.dumps(profile.DEFAULTS) == before


@pytest.mark.parametrize("partial,fragment", [
    ({"agin": {}}, "profile.agin: unknown field"),
    ({"aging": {"buckets": [30]}}, "aging.buckets: unknown field"),
    ({"aging": []}, "aging: must be an object"),
    ({"profile_version": 2}, "profile_version"),
    ({"currencies": ["usd"]}, "currencies"),
    ({"currencies": ["USD", "USD"]}, "currencies: duplicates"),
    ({"company": {"reporting_currency": "GBP"}}, "company.reporting_currency"),
    ({"company": {"fiscal_year_start_month": 13}}, "company.fiscal_year_start_month"),
    ({"entities": [{"code": "Inc", "currency": "USD"}, {"code": "Inc", "currency": "USD"}]}, "entities[1].code: duplicate"),
    ({"entities": [{"code": "Inc", "currency": "GBP"}]}, "entities[0].currency"),
    ({"entities": [{"code": "Inc", "currency": "USD", "vat": 1}]}, "entities[0].vat: unknown field"),
    ({"revenue_streams": []}, "revenue_streams: at least one"),
    ({"revenue_streams": [{"key": "Sub Scr", "label": "x", "revenue_type": "over_time", "billing_model": "monthly"}]}, "revenue_streams[0].key"),
    ({"revenue_streams": [{"key": "s", "label": "x", "revenue_type": "ratably", "billing_model": "monthly"}]}, "revenue_streams[0].revenue_type"),
    ({"revenue_streams": [{"key": "s", "label": "x", "revenue_type": "over_time", "billing_model": "weekly"}]}, "revenue_streams[0].billing_model"),
    ({"revenue_streams": [{"key": "s", "label": "", "revenue_type": "over_time", "billing_model": "monthly"}]}, "revenue_streams[0].label"),
    ({"payment_terms": {"default_days": -1}}, "payment_terms.default_days"),
    ({"payment_terms": {"default_days": 30.5}}, "payment_terms.default_days"),
    ({"payment_terms": {"basis": "net30"}}, "payment_terms.basis"),
    ({"aging": {"bucket_boundaries": [60, 30]}}, "aging.bucket_boundaries"),
    ({"aging": {"bucket_boundaries": []}}, "aging.bucket_boundaries"),
    ({"aging": {"bucket_boundaries": [1, 2, 3, 4, 5, 6]}}, "aging.bucket_boundaries"),
    ({"aging": {"basis": "posting_date"}}, "aging.basis"),
    ({"aging": {"grace_days": True}}, "aging.grace_days"),
    ({"collections": {"reminder_thresholds_days": [30, 30]}}, "collections.reminder_thresholds_days"),
    ({"collections": {"sender_name": " "}}, "collections.sender_name"),
    ({"modules": {"serials": "yes"}}, "modules.serials: true or false"),
    ({"modules": {"crm": True}}, "modules.crm: unknown field"),
    ({"targets": {"past_due_pct": 120}}, "targets.past_due_pct"),
    ({"targets": {"dso_days": 0}}, "targets.dso_days"),
])
def test_invalid_profiles_name_the_field(tmp_path, partial, fragment):
    errs = errors_for(tmp_path, partial)
    assert any(fragment in e for e in errs), errs


@pytest.mark.parametrize("content,fragment", [("{not json", "not valid JSON"), ("[1, 2]", "must be a JSON object")])
def test_unreadable_files(tmp_path, content, fragment):
    assert fragment in errors_for(tmp_path, content)[0]


def test_missing_file(tmp_path):
    with pytest.raises(profile.ProfileError, match="file not found"):
        profile.load(tmp_path / "nope.json")


def test_build_rejects_invalid_profile(tmp_path, capsys):
    bad = write(tmp_path, {"aging": {"basis": "whenever"}})
    assert build.main(["--profile", str(bad), "--out", str(tmp_path / "dist"), "--as-of", "2026-06-30"]) == 1
    assert "aging.basis" in capsys.readouterr().err


def built(tmp_path, *extra, as_of="2026-06-30"):
    out = tmp_path / f"dist{len(list(tmp_path.iterdir()))}"
    assert build.main(["--out", str(out), "--as-of", as_of, *extra]) == 0
    data = json.loads((out / "data.json").read_text())
    data["meta"].pop("generated_at")
    return data


def test_default_profile_file_matches_no_profile(tmp_path):
    explicit = write(tmp_path, profile.DEFAULTS)
    assert built(tmp_path) == built(tmp_path, "--profile", str(explicit))


def test_meta_carries_ui_profile_without_data_source(tmp_path):
    meta = built(tmp_path, "--profile", str(EXAMPLE))["meta"]
    assert meta["profile"]["company"]["name"].endswith("(fictional)")
    assert meta["profile"]["targets"] == {"dso_days": 45, "past_due_pct": 15}
    assert "data_source" not in meta["profile"]


def test_custom_buckets_flow_through_build(tmp_path):
    prof = write(tmp_path, {"aging": {"bucket_boundaries": [15, 45, 120]}})
    data = built(tmp_path, "--profile", str(prof))
    keys = ["current", "1-15", "16-45", "46-120", "120+"]
    assert data["meta"]["buckets"] == keys
    for g in data["aging"]:
        assert round(sum(g[k] for k in keys), 2) == g["gross"]
    for t in data["kpis"]["totals_by_currency"].values():
        assert set(keys) <= set(t)
    assert {i["bucket"] for i in data["invoices"] if i["bucket"]} <= set(keys)


def test_profile_revenue_types_override_derived_defaults(tmp_path):
    prof = write(tmp_path, {"revenue_streams": [
        {"key": "subscription", "label": "SaaS", "revenue_type": "over_time", "billing_model": "monthly"},
        {"key": "data", "label": "Data", "revenue_type": "point_in_time", "billing_model": "usage"},
        {"key": "hardware", "label": "Devices", "revenue_type": "over_time", "billing_model": "one_off"}]})
    rev = built(tmp_path, "--profile", str(prof))["revenue"]
    by_cat = {}
    for r in rev:
        by_cat.setdefault(r["category"], set()).add(r["timing"])
    assert by_cat["data"] == {"point_in_time"} and by_cat["hardware"] == {"over_time"}


def test_explicit_revenue_type_beats_profile():
    r = model.RevenueLine("c", "2026-01", "hardware", 1.0, "USD", timing="point_in_time")
    r.apply_timing_defaults({"hardware": "over_time"})
    assert r.timing == "point_in_time"
    d = model.RevenueLine("c", "2026-01", "hardware", 1.0, "USD")
    d.apply_timing_defaults({"hardware": "over_time"})
    assert d.timing == "over_time"
    assert "timing_derived" not in model.to_jsonable(d)


def test_currency_not_in_profile_fails_validation(tmp_path, capsys):
    prof = write(tmp_path, {"currencies": ["USD", "EUR"]})
    assert build.main(["--profile", str(prof), "--out", str(tmp_path / "d"), "--as-of", "2026-06-30"]) == 1
    assert "unknown currency ILS" in capsys.readouterr().err


@pytest.mark.parametrize("partial,fragment", [
    ({"currencies": ["USD", "EUR", "ILS", "GBP"]}, "no rate for GBP"),
    ({"currencies": ["USD", "EUR"], "company": {"reporting_currency": "EUR"}}, "only USD is supported"),
])
def test_fx_and_reporting_currency_checked(tmp_path, capsys, partial, fragment):
    prof = write(tmp_path, partial)
    assert build.main(["--profile", str(prof), "--out", str(tmp_path / "d"), "--as-of", "2026-06-30"]) == 1
    assert fragment in capsys.readouterr().err


@pytest.mark.parametrize("issue,days,basis,expected", [
    (date(2026, 1, 15), 30, "net", date(2026, 2, 14)),
    (date(2026, 1, 15), 30, "eom", date(2026, 3, 2)),
    (date(2026, 2, 3), 0, "eom", date(2026, 2, 28)),
    (date(2028, 2, 3), 15, "eom", date(2028, 3, 15)),   # leap year: Feb 29 + 15
])
def test_due_date_from_terms(issue, days, basis, expected):
    assert profile.due_date(issue, days, basis) == expected


def test_file_connector_uses_profile_terms(tmp_path):
    from ar.connectors.file import load_mapping
    (tmp_path / "inv.csv").write_text("Doc,Client,Date,Total,Terms\nA-1,X,2026-01-15,100,\nA-2,X,2026-01-15,100,10\n")
    ds = load_mapping({"files": {"invoices": {"path": "inv.csv", "columns": {
        "id": "Doc", "customer_name": "Client", "issue_date": "Date", "total": "Total", "terms_days": "Terms"}}}},
        tmp_path, terms={"default_days": 45, "basis": "eom"})
    due = {i.id: i.due_date for i in ds.invoices}
    assert due == {"A-1": date(2026, 3, 17), "A-2": date(2026, 2, 10)}   # row terms win, still end-of-month
    assert ds.customers[0].terms_days == 45
