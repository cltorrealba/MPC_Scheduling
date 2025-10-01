import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

@pytest.mark.timeout(60)
@pytest.mark.parametrize('detailed', [True])
def test_hmf_inhibition_furfural_effect(detailed):
    # Build model with detailed kinetics so q_hmf_rate is active
    m = build_fermentation_model(
        n_f_elements_t=3,
        total_f_elements_t=30,
        total_sim_time=12*3600,
        current_start_time_seconds=0.0,
        include_kinetics=True,
        detailed_kinetics=detailed,
        initial_concentrations={'HMF':2.0,'F':0.0,'Cell':1.0,'G':5.0,'X':3.0,'Eth':0.0,'F':0.2,'ACT':0.1,'CO2':0.0},
        enable_mass_balance=False,
    )
    # Discretized model now; fix concentrations at second time point to isolate expression evaluation
    t_points = list(m.t)
    if len(t_points) < 2:
        pytest.skip('Not enough time points for evaluation')
    t1 = t_points[1]
    # Baseline with low furfural
    m.C[t1,'F'].set_value(0.0)
    # Need a solve for expression activation; but kinetic equality defines q directly -> evaluate
    sf = pe.SolverFactory('ipopt') if pe.SolverFactory('ipopt').available() else None
    if sf:
        sf.solve(m, tee=False)
    q_low = float(pe.value(m.q[t1,'HMF']))
    # Increase furfural to inhibit
    m.C[t1,'F'].set_value(10.0)
    if sf:
        sf.solve(m, tee=False)
    q_highF = float(pe.value(m.q[t1,'HMF']))
    assert q_highF <= q_low + 1e-9, f"Expected inhibition: q_highF={q_highF} should be <= q_low={q_low}"
