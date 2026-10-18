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

1. Put exports in `data/private/` (gitignored).
2. Point `config.json` at the `file` connector and a column mapping.
3. `python3 build.py`

## Data hygiene

`scripts/check_denylist.py` blocks commits (pre-commit hook) and CI runs that contain denied terms. The term list lives outside the repo (`~/.config/ar-dashboard/denylist.txt` locally, the `AR_DENYLIST` secret in CI).

One-time setup after cloning:

```sh
git config core.hooksPath .githooks
```

See [FEATURES.md](FEATURES.md) for the feature scope.
