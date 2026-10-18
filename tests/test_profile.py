import json
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
    ({"aging": {"bucket_boundaries": [1, 2, 3, 4, 5, 6, 7]}}, "aging.bucket_boundaries"),
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


def test_profile_does_not_change_output_yet(tmp_path):
    """Task 1 only loads and checks the profile; the dashboard still uses its built-in rules."""
    def built(*extra):
        out = tmp_path / ("dist" + str(len(extra)))
        assert build.main(["--out", str(out), "--as-of", "2026-06-30", *extra]) == 0
        data = json.loads((out / "data.json").read_text())
        data["meta"].pop("generated_at")
        return data
    assert built() == built("--profile", str(EXAMPLE))
