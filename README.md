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
python3 build.py            # sample data -> dist/data.json
python3 -m http.server -d dist 8000
```

## Using real data

1. Put CSV/XLSX exports in `data/private/` (gitignored; `*.xlsx` is ignored repo-wide too).
2. Copy `mappings/example.json` and set the header names from your exports. Only `invoices` is required: customers are derived from invoice rows if there is no customers file, and revenue is derived from invoices if there is no revenue file.
3. In `config.json` set `"connector": "file"` and point `options.file.mapping` at your mapping.
4. `python3 build.py` validates everything first. Errors name the file, row and field.

Sign conventions: payments must be positive. If your export shows receipts as negatives or in parentheses, add `"negate": true` to the payments mapping.

| Connector | Status |
|---|---|
| `sample` | Fictional, deterministic demo data |
| `file` | CSV / XLSX + column mapping |
| `stripe` | Stub: interface defined, not implemented |

## Data hygiene

`scripts/check_denylist.py` blocks commits (pre-commit hook) and CI runs that contain denied terms. The term list lives outside the repo (`~/.config/ar-dashboard/denylist.txt` locally, the `AR_DENYLIST` secret in CI).

One-time setup after cloning:

```sh
git config core.hooksPath .githooks
```

See [FEATURES.md](FEATURES.md) for the feature scope.
