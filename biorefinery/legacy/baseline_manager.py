import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

BASELINE_ENV_REFRESH = "BIOREF_REFRESH_BASELINES"  # if '1', refresh all provided sections
BASELINE_FILE_ENV = "BIOREF_BASELINE_FILE"          # override default path
DEFAULT_BASELINE_PATH = Path("tests/legacy_unified_baseline.json")

SECTION_DYNAMIC = "dynamic_finals"
SECTION_SERIES = "series_concentrations"
SECTION_RATES = "series_rates"  # future


def _baseline_path() -> Path:
    custom = os.getenv(BASELINE_FILE_ENV, "").strip()
    if custom:
        return Path(custom)
    return DEFAULT_BASELINE_PATH


def load_baseline() -> Dict[str, Any]:
    p = _baseline_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_baseline(data: Dict[str, Any]):
    p = _baseline_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # ensure stable ordering for diffs
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def maybe_update_section(section: str, payload: Dict[str, Any]) -> bool:
    """Update (or insert) a section in the unified baseline file.

    Returns True if a refresh occurred (and test should skip afterwards).
    Refresh is triggered when env BIOREF_REFRESH_BASELINES == '1'.
    """
    refresh_all = os.getenv(BASELINE_ENV_REFRESH, "0") == "1"
    if not refresh_all:
        return False
    data = load_baseline()
    data[section] = payload
    save_baseline(data)
    return True


def get_section(section: str) -> Optional[Dict[str, Any]]:
    data = load_baseline()
    return data.get(section)


def summarize_sections() -> Dict[str, bool]:
    data = load_baseline()
    return {SECTION_DYNAMIC: SECTION_DYNAMIC in data,
            SECTION_SERIES: SECTION_SERIES in data,
            SECTION_RATES: SECTION_RATES in data}
