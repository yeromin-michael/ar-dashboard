"""Connector contract: anything that can produce a Dataset.

A connector is a function `load(options: dict, as_of: date) -> Dataset`.
Register it in REGISTRY under the name used in config.json -> "connector".
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from ..model import Dataset

Loader = Callable[[dict, date], Dataset]


def _sample(options: dict, as_of: date) -> Dataset:
    from .sample import load
    return load(options, as_of)


def _file(options: dict, as_of: date) -> Dataset:
    from .file import load
    return load(options, as_of)


def _stripe(options: dict, as_of: date) -> Dataset:
    from .stripe import load
    return load(options, as_of)


REGISTRY: dict[str, Loader] = {
    "sample": _sample,
    "file": _file,
    "stripe": _stripe,
}


def get(name: str) -> Loader:
    try:
        return REGISTRY[name]
    except KeyError:
        raise SystemExit(f"unknown connector '{name}'; choose from {sorted(REGISTRY)}")
