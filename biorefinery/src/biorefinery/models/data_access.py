"""Utilities to access raw biorefinery data files.

Provides a single function `get_data_path(name)` that resolves the CSV location.
Falls back to legacy path if file not yet moved.
"""
from __future__ import annotations
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_NEW_DATA = _REPO_ROOT / "biorefinery" / "data" / "raw"
_LEGACY = _REPO_ROOT / "biorefinery_models"


def get_data_path(filename: str) -> pathlib.Path:
    """Return path to a data file (CSV) searching new location first.

    Parameters
    ----------
    filename : str
        Base name of the file (e.g., 'Glucose.csv').
    """
    new_path = _NEW_DATA / filename
    if new_path.exists():
        return new_path
    legacy_path = _LEGACY / filename
    if legacy_path.exists():
        return legacy_path
    raise FileNotFoundError(f"No data file found for {filename} in {_NEW_DATA} or {legacy_path}")
