from __future__ import annotations
import json, csv, pathlib, datetime, math
from typing import Any, Dict

ComparisonPayload = Dict[str, Any]


def load_comparison(path: str | pathlib.Path) -> ComparisonPayload:
    p = pathlib.Path(path)
    with p.open('r', encoding='utf-8') as f:
        return json.load(f)


def _safe(v):
    if v is None:
        return None
    try:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
    except Exception:
        pass
    return v


def summarize_kpis(payload: ComparisonPayload) -> Dict[str, Any]:
    mod = payload.get('modular', {})
    leg = payload.get('legacy', {})
    comp = payload.get('comparison', {})
    meta = payload.get('meta', {})
    mod_kpis = mod.get('kpis', mod)
    summary = {
        'timestamp': datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'horizon_h': meta.get('horizon_h'),
        'nfe': meta.get('nfe'),
        'sched_periods': meta.get('sched_periods'),
        'mod_final_ethanol': _safe(mod_kpis.get('final_ethanol_conc')),
        'leg_final_ethanol': _safe(leg.get('final_ethanol_conc')),
        'delta_ethanol': _safe(comp.get('ethanol_conc_delta')),
        'mod_final_hold_up': _safe(mod_kpis.get('final_hold_up')),
        'leg_final_hold_up': _safe(leg.get('final_hold_up')),
        'delta_hold_up': _safe(comp.get('hold_up_delta')),
        'legacy_term_cond': leg.get('termination_condition'),
        'legacy_status': leg.get('status'),
        'legacy_elapsed_s': leg.get('elapsed_s'),
    }
    return summary


CSV_HEADER = [
    'timestamp','horizon_h','nfe','sched_periods',
    'mod_final_ethanol','leg_final_ethanol','delta_ethanol',
    'mod_final_hold_up','leg_final_hold_up','delta_hold_up',
    'legacy_term_cond','legacy_status','legacy_elapsed_s'
]


def write_csv_row(row: Dict[str, Any], path: str | pathlib.Path, append: bool = True) -> None:
    p = pathlib.Path(path)
    new_file = not p.exists() or not append
    mode = 'a' if append else 'w'
    with p.open(mode, newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new_file:
            w.writeheader()
        # Only keep known columns
        filtered = {k: row.get(k) for k in CSV_HEADER}
        w.writerow(filtered)
