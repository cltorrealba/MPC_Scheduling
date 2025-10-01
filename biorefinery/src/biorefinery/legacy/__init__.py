# Legacy comparison utilities package
from .baseline_manager import (
    load_baseline, save_baseline, maybe_update_section, get_section,
    summarize_sections, SECTION_DYNAMIC, SECTION_SERIES, SECTION_RATES
)
from .tolerances import (
    dynamic_tolerances, series_tolerances, rates_tolerances
)
__all__ = [
    'load_baseline','save_baseline','maybe_update_section','get_section','summarize_sections',
    'SECTION_DYNAMIC','SECTION_SERIES','SECTION_RATES',
    'dynamic_tolerances','series_tolerances','rates_tolerances'
]
