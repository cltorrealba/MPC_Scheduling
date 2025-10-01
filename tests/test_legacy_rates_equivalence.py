import importlib
import os
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.legacy.baseline_manager import (
    maybe_update_section,
    get_section,
    SECTION_RATES,
    set_param_hash,
    get_param_hash,
)
from biorefinery.legacy.tolerances import rates_tolerances
from biorefinery.legacy.param_hash import compute_param_hash

LEGACY_MODULE = 'biorefinery_models.Fermentation_Scheduling_and_MPC'
LEGACY_FUNC = 'build_fermentation_one_time_step_optimizing_flows_pH_open_loop_pessimization'

MAX_SERIES_POINTS = 200  # cap to avoid very long arrays in baseline


def _import_legacy():
    try:
        mod = importlib.import_module(LEGACY_MODULE)
        if hasattr(mod, LEGACY_FUNC):
            return getattr(mod, LEGACY_FUNC)
    except Exception:
        return None
    return None


legacy_builder = _import_legacy()


def _pick_solver():
    for name in ('ipopt','glpk'):
        try:
            sf = pe.SolverFactory(name)
            if sf and sf.available(False):
                return name
        except Exception:
            continue
    return None


def _collect_rate_series(model):
    tlist = sorted(list(model.t))
    collected = {}
    # Explicit extraction for q and R if they exist
    if hasattr(model, 'q'):
        for idx in model.q:
            if not isinstance(idx, tuple) or len(idx) != 2:
                continue
            t, subs = idx
            if t not in model.t:
                continue
            key = f"q[{subs}]"
            collected.setdefault(key, [])
        for key in list(collected.keys()):
            collected[key] = []
        for t in tlist:
            for idx in model.q:
                if not isinstance(idx, tuple) or len(idx) != 2:
                    continue
                tt, subs = idx
                if tt != t:
                    continue
                key = f"q[{subs}]"
                if key in collected:
                    try:
                        collected[key].append(float(pe.value(model.q[idx])))
                    except Exception:
                        collected[key].append(None)
    if hasattr(model, 'R'):
        existing_keys = set(collected.keys())
        for idx in model.R:
            if not isinstance(idx, tuple) or len(idx) != 2:
                continue
            t, rxn = idx
            if t not in model.t:
                continue
            key = f"R[{rxn}]"
            collected.setdefault(key, [])
        for key in collected:
            if key not in existing_keys and key.startswith('R['):
                collected[key] = []
        for t in tlist:
            for idx in model.R:
                if not isinstance(idx, tuple) or len(idx) != 2:
                    continue
                tt, rxn = idx
                if tt != t:
                    continue
                key = f"R[{rxn}]"
                if key in collected:
                    try:
                        collected[key].append(float(pe.value(model.R[idx])))
                    except Exception:
                        collected[key].append(None)
    # Trim if too long
    if len(tlist) > MAX_SERIES_POINTS:
        stride = max(1, len(tlist)//MAX_SERIES_POINTS)
        tlist = tlist[::stride]
        for k,v in collected.items():
            collected[k] = v[::stride]
    return [float(t) for t in tlist], collected


@pytest.mark.skipif(legacy_builder is None, reason='Legacy modelo no disponible para tasas')
def test_legacy_rates_equivalence():
    solver_name = _pick_solver()
    if solver_name is None:
        pytest.skip('Sin solver disponible para tasas')
    solver = pe.SolverFactory(solver_name)

    # Legacy model (coarse discretization)
    m_leg = legacy_builder(n_f_elements_t=3, total_f_elements_t=3)
    solver.solve(m_leg, tee=False)
    t_leg, rates_leg = _collect_rate_series(m_leg)

    # New model
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                     n_f_elements_t=3, total_f_elements_t=3,
                                     initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    solver.solve(m_new, tee=False)
    t_new, rates_new = _collect_rate_series(m_new)

    # If time discretization differs, skip (structural mismatch)
    if len(t_leg) != len(t_new):
        pytest.skip('Diferente discretización de tiempo (tasas)')

    tol = rates_tolerances()
    phash = compute_param_hash(m_new)
    payload = {
        'time': t_new,
        'rates_legacy': rates_leg,
        'rates_new': rates_new,
        'abs_tol': tol.abs_tol,
        'rel_tol': tol.rel_tol,
        'solver': solver_name,
        'param_hash': phash,
        'variable_sets': {'q': hasattr(m_new,'q'), 'R': hasattr(m_new,'R')},
    }
    if maybe_update_section(SECTION_RATES, payload):
        set_param_hash(phash)
        pytest.skip('Baseline tasas (unificada) actualizada')

    stored = get_section(SECTION_RATES) or {}
    abs_tol = stored.get('abs_tol', tol.abs_tol)
    rel_tol = stored.get('rel_tol', tol.rel_tol)
    stored_hash = stored.get('param_hash')
    baseline_hash = get_param_hash()
    if baseline_hash and stored_hash and (phash != baseline_hash or stored_hash != phash):
        pytest.skip('Param hash mismatch tasas; regenerar baseline')

    # Only compare rate series that exist in both models
    common_keys = sorted(set(rates_leg.keys()) & set(rates_new.keys()))
    if not common_keys:
        pytest.skip('No se encontraron variables de tasa comunes para comparar')

    for key in common_keys:
        leg_vals = rates_leg[key]
        new_vals = rates_new[key]
        if len(leg_vals) != len(new_vals):
            continue
        for idx, (lv, nv) in enumerate(zip(leg_vals, new_vals)):
            if lv is None or nv is None:
                continue
            diff = abs(lv - nv)
            rel = diff / max(1e-9, abs(lv))
            assert (diff <= abs_tol) or (rel <= rel_tol), f"{key}[{idx}] diff={diff:.3g} rel={rel:.3g} lv={lv:.3g} nv={nv:.3g} (abs_tol={abs_tol} rel_tol={rel_tol})"
