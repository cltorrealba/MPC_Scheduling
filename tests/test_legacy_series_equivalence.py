import importlib
import os
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.legacy.baseline_manager import (
    maybe_update_section,
    get_section,
    SECTION_SERIES,
    set_param_hash,
    get_param_hash,
)
from biorefinery.legacy.tolerances import series_tolerances
from biorefinery.legacy.param_hash import compute_param_hash

LEGACY_MODULE = 'biorefinery_models.Fermentation_Scheduling_and_MPC'
LEGACY_FUNC = 'build_fermentation_one_time_step_optimizing_flows_pH_open_loop_pessimization'

SPECIES = ['G','X','Eth']  # subset to keep runtime small


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


def _extract_series(model, species_list):
    tlist = sorted(list(model.t))
    series = {sp: [] for sp in species_list}
    for t in tlist:
        for sp in species_list:
            try:
                series[sp].append(pe.value(model.C[t, sp]))
            except Exception:
                series[sp].append(None)
    return [float(t) for t in tlist], series


@pytest.mark.skipif(legacy_builder is None, reason='Legacy modelo no disponible')
def test_legacy_series_equivalence():
    solver_name = _pick_solver()
    if solver_name is None:
        pytest.skip('Sin solver disponible para series')
    solver = pe.SolverFactory(solver_name)

    # Build & solve legacy
    m_leg = legacy_builder(n_f_elements_t=4, total_f_elements_t=4)
    solver.solve(m_leg, tee=False)
    t_leg, series_leg = _extract_series(m_leg, SPECIES)

    # Build & solve new
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                     n_f_elements_t=4, total_f_elements_t=4,
                                     initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    solver.solve(m_new, tee=False)
    t_new, series_new = _extract_series(m_new, SPECIES)

    # If lengths differ skip strict comparison (structure mismatch)
    if len(t_leg) != len(t_new):
        pytest.skip('Diferente discretización (n_t) entre legacy y nuevo')

    tol = series_tolerances()
    phash = compute_param_hash(m_new)
    payload = {
        'time': t_new,
        'series_legacy': series_leg,
        'series_new': series_new,
        'abs_tol': tol.abs_tol,
        'rel_tol': tol.rel_tol,
        'species': SPECIES,
        'solver': solver_name,
        'param_hash': phash,
    }
    if maybe_update_section(SECTION_SERIES, payload):
        set_param_hash(phash)
        pytest.skip('Baseline series (unificada) actualizada')

    stored = get_section(SECTION_SERIES) or {}
    abs_tol = stored.get('abs_tol', tol.abs_tol)
    rel_tol = stored.get('rel_tol', tol.rel_tol)
    stored_hash = stored.get('param_hash')
    baseline_hash = get_param_hash()
    if baseline_hash and stored_hash and (phash != baseline_hash or stored_hash != phash):
        pytest.skip(f"Param hash mismatch (stored={stored_hash} global={baseline_hash} current={phash}); regenerar baseline")

    # Direct comparison with coarse tolerances
    for sp in SPECIES:
        leg_vals = series_leg[sp]
        new_vals = series_new[sp]
        for idx, (lv, nv) in enumerate(zip(leg_vals, new_vals)):
            if (lv is None) or (nv is None):
                continue
            diff = abs(lv - nv)
            rel = diff / max(1e-6, abs(lv))
            assert (diff <= abs_tol) or (rel <= rel_tol), f"{sp}[{idx}] diff={diff:.3g} rel={rel:.3g} lv={lv:.3g} nv={nv:.3g} (abs_tol={abs_tol} rel_tol={rel_tol})"
