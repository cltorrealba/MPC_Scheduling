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
GLOBAL_PARAM_HASH_KEY = "param_hash"


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
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def maybe_update_section(section: str, payload: Dict[str, Any]) -> bool:
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
            SECTION_RATES: SECTION_RATES in data,
            GLOBAL_PARAM_HASH_KEY: GLOBAL_PARAM_HASH_KEY in data}


def set_param_hash(param_hash: str, force: bool = False) -> bool:
    """Store a global param hash. Returns True if written (refresh or force)."""
    refresh_all = os.getenv(BASELINE_ENV_REFRESH, "0") == "1"
    data = load_baseline()
    if (not refresh_all) and (GLOBAL_PARAM_HASH_KEY in data) and not force:
        return False
    data[GLOBAL_PARAM_HASH_KEY] = param_hash
    save_baseline(data)
    return True


def get_param_hash() -> Optional[str]:
    return load_baseline().get(GLOBAL_PARAM_HASH_KEY)
