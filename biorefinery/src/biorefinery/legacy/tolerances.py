import os
from dataclasses import dataclass

TOL_MODE_ENV = "BIOREF_TOLERANCE_MODE"  # values: lenient (default), strict

@dataclass(frozen=True)
class Tolerances:
    abs_tol: float
    rel_tol: float

LENIENT_DYNAMIC = Tolerances(abs_tol=5e-2, rel_tol=5e-2)
STRICT_DYNAMIC = Tolerances(abs_tol=2e-2, rel_tol=2e-2)

LENIENT_SERIES = Tolerances(abs_tol=1e-1, rel_tol=8e-2)
STRICT_SERIES = Tolerances(abs_tol=5e-2, rel_tol=5e-2)

LENIENT_RATES = Tolerances(abs_tol=2e-1, rel_tol=1.0)
STRICT_RATES = Tolerances(abs_tol=8e-2, rel_tol=6e-2)


def _mode() -> str:
    return os.getenv(TOL_MODE_ENV, "lenient").lower().strip() or "lenient"


def dynamic_tolerances() -> Tolerances:
    return STRICT_DYNAMIC if _mode() == "strict" else LENIENT_DYNAMIC


def series_tolerances() -> Tolerances:
    return STRICT_SERIES if _mode() == "strict" else LENIENT_SERIES


def rates_tolerances() -> Tolerances:
    return STRICT_RATES if _mode() == "strict" else LENIENT_RATES
