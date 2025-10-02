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
    horizon = meta.get('horizon_h') or 0
    mod_eth = _safe(mod_kpis.get('final_ethanol_conc'))
    productivity = None
    try:
        if mod_eth is not None and horizon and horizon > 0:
            productivity = mod_eth / horizon
    except Exception:
        productivity = None
    meta_block = payload.get('meta', {})
    legacy_n_vars = payload.get('legacy', {}).get('n_vars')
    legacy_n_cons = payload.get('legacy', {}).get('n_cons')
    modular_elapsed = meta_block.get('modular_elapsed_s')
    legacy_term = leg.get('termination_condition')
    # Feasibility heuristic
    feasible = True
    if legacy_term in {'infeasible','exception'}:
        feasible = False
    if productivity is None:
        feasible = False
    return {
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
        'productivity_ethanol_per_h': productivity,
        'legacy_term_cond': leg.get('termination_condition'),
        'legacy_status': leg.get('status'),
        'legacy_elapsed_s': leg.get('elapsed_s'),
        'modular_elapsed_s': modular_elapsed,
        'legacy_n_vars': legacy_n_vars,
        'legacy_n_cons': legacy_n_cons,
        'legacy_feasible_flag': int(feasible),
        'git_commit': meta_block.get('git_commit'),
        'git_dirty': meta_block.get('git_dirty'),
        'python_version': meta_block.get('python_version'),
    }

CSV_HEADER = [
    'timestamp','horizon_h','nfe','sched_periods',
    'mod_final_ethanol','leg_final_ethanol','delta_ethanol',
    'mod_final_hold_up','leg_final_hold_up','delta_hold_up',
    'productivity_ethanol_per_h',
    'legacy_term_cond','legacy_status','legacy_elapsed_s',
    'modular_elapsed_s','legacy_n_vars','legacy_n_cons','legacy_feasible_flag',
    'git_commit','git_dirty','python_version'
]

def write_csv_row(row: Dict[str, Any], path: str | pathlib.Path, append: bool = True) -> None:
    p = pathlib.Path(path)
    new_file = not p.exists() or not append
    mode = 'a' if append else 'w'
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    # Header validation: if file exists and header mismatches, rotate old file
    if not new_file:
        try:
            first_line = p.read_text(encoding='utf-8').splitlines()[0]
            existing_cols = first_line.strip().split(',')
            if existing_cols != CSV_HEADER:
                rotated = p.with_suffix('.old')
                p.rename(rotated)
                new_file = True
        except Exception:
            pass
    with p.open(mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new_file:
            writer.writeheader()
        filtered = {k: row.get(k) for k in CSV_HEADER}
        writer.writerow(filtered)
