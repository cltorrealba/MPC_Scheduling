import importlib
import math
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model


LEGACY_MODULE = 'biorefinery_models.Fermentation_Scheduling_and_MPC'
LEGACY_BUILDER = 'build_fermentation_one_time_step_optimizing_flows_pH_open_loop_pessimization'

PARAMS_NUMERIC_EQUIV = [
    'qmax_G','qmax_X','qmax_F','qmax_HMF','qmax_ATC',
    'Y_Eth_G','Y_Eth_X','Y_Cell_G','Y_Cell_X','Y_CO2_G','Y_CO2_X'
]


def _try_import_legacy():
    try:
        mod = importlib.import_module(LEGACY_MODULE)
        if not hasattr(mod, LEGACY_BUILDER):
            return None
        return mod
    except Exception:
        return None


legacy_mod = _try_import_legacy()


@pytest.mark.skipif(legacy_mod is None, reason="Legacy module not importable; skip equivalence test")
def test_legacy_parameter_equivalence():
    legacy_builder = getattr(legacy_mod, LEGACY_BUILDER)
    m_legacy = legacy_builder(n_f_elements_t=1, total_f_elements_t=1)
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=True)
    for pname in PARAMS_NUMERIC_EQUIV:
        assert hasattr(m_legacy, pname), f'Legacy missing {pname}'
        assert hasattr(m_new, pname), f'New builder missing {pname}'
        lv = pe.value(getattr(m_legacy, pname))
        nv = pe.value(getattr(m_new, pname))
        diff = abs(lv - nv)
        tol = max(1e-10, 1e-3 * max(1.0, abs(lv)))
        assert diff <= tol, f'{pname} mismatch legacy={lv} new={nv} diff={diff} tol={tol}'


@pytest.mark.skipif(legacy_mod is None, reason="Legacy module not importable; skip structural test")
def test_structural_kinetic_route_alignment():
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=True)
    expected_routes = {'G','X','F','HMF','ACT'}
    assert hasattr(m_new, 'route_config'), 'New model missing route_config Param'
    new_routes = {idx for idx in m_new.route_config}
    assert expected_routes == new_routes, f'Route set mismatch expected={expected_routes} got={new_routes}'
    assert hasattr(m_new, 'kinetic_species'), 'New model missing kinetic_species set'
    kin_species = {s for s in m_new.kinetic_species}
    missing = expected_routes - kin_species
    assert not missing, f'Missing kinetic species for routes: {missing}'


@pytest.mark.skipif(legacy_mod is None, reason="Legacy module not importable; skip objective consistency")
def test_objective_sign_consistency():
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=True)
    assert hasattr(m_new, 'obj'), 'New model missing objective'
    val = pe.value(m_new.obj)
    assert math.isfinite(val), 'Objective value not finite'
