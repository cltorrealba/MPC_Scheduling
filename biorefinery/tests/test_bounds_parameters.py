import math
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

INIT_CONC = {'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0}

def _build(max_c, min_M):
    return build_fermentation_model(
        n_f_elements_t=2,
        total_f_elements_t=2,
        total_sim_time=12*3600,
        current_start_time_seconds=0.0,
        include_kinetics=True,
        detailed_kinetics=False,
        initial_concentrations=INIT_CONC,
        enable_mass_balance=True,
        feed_control=False,
        max_concentration=max_c,
        min_hold_up=min_M,
        rate_scale=10.0,
    )

def test_concentration_upper_bound_respected():
    m = _build(150.0, 120.0)
    # After discretization bounds are on each var; just assert bound set, not solved
    for idx in m.C:
        ub = m.C[idx].ub
        assert math.isclose(ub, 150.0, rel_tol=0, abs_tol=1e-12)

def test_hold_up_lower_bound_respected():
    m = _build(180.0, 80.0)
    for tau in m.t:
        lb = m.M[tau].lb
        assert math.isclose(lb, 80.0, rel_tol=0, abs_tol=1e-12)

def test_bounds_affect_hash_indirectly():
    # Build two models, check differing max_concentration changes at least one ub
    m1 = _build(150.0, 80.0)
    m2 = _build(200.0, 80.0)
    any_diff = False
    for idx in m1.C:
        if not math.isclose(m1.C[idx].ub, m2.C[idx].ub):
            any_diff = True
            break
    assert any_diff, "Expected difference in concentration upper bounds"
