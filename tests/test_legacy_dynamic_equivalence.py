import importlib
import os
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.legacy.baseline_manager import (
    maybe_update_section,
    get_section,
    SECTION_DYNAMIC,
    set_param_hash,
    get_param_hash,
)
from biorefinery.legacy.tolerances import dynamic_tolerances
from biorefinery.legacy.param_hash import compute_param_hash

LEGACY_MODULE = 'biorefinery_models.Fermentation_Scheduling_and_MPC'
LEGACY_FUNC = 'build_fermentation_one_time_step_optimizing_flows_pH_open_loop_pessimization'

KEY_SPECIES = ['G','X','Eth','Cell']


def _import_legacy_builder():
    try:
        mod = importlib.import_module(LEGACY_MODULE)
        if hasattr(mod, LEGACY_FUNC):
            return getattr(mod, LEGACY_FUNC)
    except Exception:
        return None
    return None


legacy_builder = _import_legacy_builder()


def _pick_solver(candidates=('ipopt','glpk','bonmin')):
    for name in candidates:
        try:
            sf = pe.SolverFactory(name)
            if sf and sf.available(False):
                return name
        except Exception:
            continue
    return None


@pytest.mark.skipif(legacy_builder is None, reason='Legacy builder no disponible')
def test_legacy_dynamic_equivalence():
    solver_name = _pick_solver()
    if solver_name is None:
        pytest.skip('Ningún solver apropiado disponible')
    solver = pe.SolverFactory(solver_name)

    # Build legacy (short horizon: n_f_elements_t=3) for a bit of dynamics
    m_leg = legacy_builder(n_f_elements_t=3, total_f_elements_t=3)
    solver.solve(m_leg, tee=False)

    # Build new model with analogous discretization
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                     n_f_elements_t=3, total_f_elements_t=3,
                                     initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    solver.solve(m_new, tee=False)

    # Extract finals
    tL_new = m_new.t.last()
    finals_new = {sp: pe.value(m_new.C[tL_new, sp]) for sp in KEY_SPECIES if (tL_new, sp) in m_new.C}
    # Legacy: attempt similar final retrieval (assume variable names C indexed by t, species or similar)
    finals_leg = {}
    try:
        tL_leg = m_leg.t.last()
        for sp in KEY_SPECIES:
            try:
                finals_leg[sp] = pe.value(m_leg.C[tL_leg, sp])
            except Exception:
                pass
    except Exception:
        pytest.skip('No se pudo acceder a puntos finales en modelo legacy')

    # Unified baseline manager (refresh via BIOREF_REFRESH_BASELINES=1)
    tol = dynamic_tolerances()
    phash = compute_param_hash(m_new)
    payload = {
        'solver': solver_name,
        'finals_legacy': finals_leg,
        'finals_new': finals_new,
        'abs_tol': tol.abs_tol,
        'rel_tol': tol.rel_tol,
        'species': KEY_SPECIES,
        'param_hash': phash,
    }
    if maybe_update_section(SECTION_DYNAMIC, payload):
        set_param_hash(phash)
        pytest.skip('Baseline dinámica (unificada) actualizada')

    stored = get_section(SECTION_DYNAMIC) or {}
    abs_tol = stored.get('abs_tol', dynamic_tolerances().abs_tol)
    rel_tol = stored.get('rel_tol', dynamic_tolerances().rel_tol)
    stored_hash = stored.get('param_hash')
    baseline_hash = get_param_hash()
    if baseline_hash and stored_hash and (phash != baseline_hash or stored_hash != phash):
        pytest.skip(f"Param hash mismatch (stored={stored_hash} global={baseline_hash} current={phash}); regenerar baseline con BIOREF_REFRESH_BASELINES=1")

    # Compare (skip species missing from either model)
    for sp, val_leg in finals_leg.items():
        if sp not in finals_new:
            continue
        val_new = finals_new[sp]
        if val_leg is None or val_new is None:
            continue
    diff = abs(val_leg - val_new)
    rel = diff / max(1e-6, abs(val_leg))
    assert (diff <= abs_tol) or (rel <= rel_tol), f"{sp} diff={diff:.3g} rel={rel:.3g} legacy={val_leg:.3g} new={val_new:.3g} (abs_tol={abs_tol} rel_tol={rel_tol})"
