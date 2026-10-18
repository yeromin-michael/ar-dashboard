"""Stripe connector (not implemented yet).

Planned mapping: Customer -> Customer, Invoice (status open/paid) -> Invoice,
Charge/PaymentIntent applied to an invoice -> Payment(kind="payment"),
CreditNote -> Payment(kind="credit"). The API key is read from the env var
named in options["api_key_env"]; it is never stored in config.
"""
from __future__ import annotations

from datetime import date

from ..model import Dataset


def load(options: dict, as_of: date) -> Dataset:
    raise SystemExit("stripe connector is not implemented yet; use 'sample' or 'file'")
