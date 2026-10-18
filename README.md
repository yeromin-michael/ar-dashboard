# AR Dashboard

Accounts-receivable dashboard for a B2B company: aging, collections, revenue recognition, dunning and per-customer views.

The repo ships with **synthetic sample data only**. Real data is plugged in through connectors and never committed.

## How it works

```
connector (sample | file | api)  ->  ar/ (model + aging)  ->  dist/data.json  ->  web/index.html
```

- **Connectors** (`ar/connectors/`) load customers, invoices and payments into one canonical model.
- **Aging is computed** from due dates and an as-of date at build time, never stored.
- **The UI** (`web/`) contains only code and reads `data.json`.

## Quick start

```sh
python3 build.py                         # sample data -> dist/data.json (stdlib only)
python3 -m http.server -d dist 8000      # static preview

# or the server (security headers, /api/ar, /health):
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --port 8080
```

Build for a fixed date: `python3 build.py --as-of 2026-06-30`. Run tests with `pytest -q`.

## Releasing

```sh
./release.sh minor "what changed"    # runs deny-list + tests + build, bumps VERSION, tags vX.Y.Z, pushes
```

Every release is a git tag, so any version can be restored with `git checkout vX.Y.Z`. The version shows in the sidebar badge.

## Using real data

1. Put CSV/XLSX exports in `data/private/` (gitignored; `*.xlsx` is ignored repo-wide too).
2. Copy `mappings/example.json` and set the header names from your exports. Only `invoices` is required: customers are derived from invoice rows if there is no customers file, and revenue is derived from invoices if there is no revenue file.
3. In `config.json` set `"connector": "file"` and point `options.file.mapping` at your mapping.
4. `python3 build.py` validates everything first. Errors name the file, row and field.

Revenue type: a revenue file may include a `timing` column (`over time` / `point in time`; `ratably` and `PIT` are accepted too). Without it, the type is derived from the category.

Sign conventions: payments must be positive. If your export shows receipts as negatives or in parentheses, add `"negate": true` to the payments mapping.

| Connector | Status |
|---|---|
| `sample` | Fictional, deterministic demo data |
| `file` | CSV / XLSX + column mapping |
| `stripe` | Stub: interface defined, not implemented |

## Company profile

A profile describes how the company's AR works: entities and currencies, revenue streams (with revenue type and billing model), default payment terms, aging buckets and basis, collections thresholds, modules and targets. It will be filled in by the onboarding form and reviewed before real data is loaded.

- Start from `profiles/example.json` (fictional). Keep the real one in `data/private/`, because it is client-confidential.
- Point `config.json` at it with `"profile": "data/private/profile.json"`, or pass `--profile`.
- Sections you leave out use the defaults in `ar/profile.py`, which match the dashboard's built-in behavior. With no profile, nothing changes.
- `build.py` checks the profile first and names each bad field, e.g. `aging.bucket_boundaries: 1-5 increasing day counts`.

What the profile controls:

| Section | Effect |
|---|---|
| `aging` | Bucket boundaries (up to 5, e.g. `[15, 45, 90]` gives Current, 1–15, 16–45, 46–90, 90+), basis (`due_date`, or `invoice_date` to age from issue) and grace days before an invoice counts as overdue |
| `revenue_streams` | Category labels and order, and the revenue type for lines whose export doesn't state one |
| `payment_terms` | Due date when an export row has neither a due date nor terms (`eom` counts from the end of the invoice month) |
| `currencies` | Currencies the data may use; each non-USD one needs a rate in `config.json` `fx_to_usd` |
| `collections` | Dunning thresholds, the "escalate" flag and the reminder sign-off |
| `modules` | Hide Revenue Rec, Dunning, Up Next (`whats_next`), usage billing or serials |
| `targets` | DSO and past-due targets on the overview, marked met or missed |
| `company` | Name in the sidebar. Reporting currency must be USD for now |

`entities`, `fiscal_year_start_month`, `billing_model` and `data_source` are recorded but not used yet; the onboarding check will compare them with the export.

## Data hygiene

`scripts/check_denylist.py` blocks commits (pre-commit hook) and CI runs that contain denied terms. The term list lives outside the repo (`~/.config/ar-dashboard/denylist.txt` locally, the `AR_DENYLIST` secret in CI).

One-time setup after cloning:

```sh
git config core.hooksPath .githooks
```

See [FEATURES.md](FEATURES.md) for the feature scope.
