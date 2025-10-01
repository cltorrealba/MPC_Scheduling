import json, os, math
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

def _solve(model):
    solver = pe.SolverFactory('ipopt')
    try:
        res = solver.solve(model, tee=False)
    except Exception:
        return None
    return model

def extract_eth_M(model):
    tL = model.t.last()
    Eth = float(pe.value(model.C[tL,'Eth']))
    M = float(pe.value(model.M[tL]))
    return Eth, M

def build_and_run(rate_scale):
    m = build_fermentation_model(n_f_elements_t=2, total_f_elements_t=2, total_sim_time=12*3600,
                                 current_start_time_seconds=0.0, include_kinetics=True,
                                 detailed_kinetics=False, initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0},
                                 enable_mass_balance=True, feed_control=False, max_concentration=200.0, min_hold_up=100.0,
                                 rate_scale=rate_scale)
    # Objective is default (maximize Eth -> minimize -Eth)
    _solve(m)
    return extract_eth_M(m)

def test_rate_scale_invariance():
    base = build_and_run(1.0)
    scaled = build_and_run(50.0)
    # Ethanol and M should be nearly identical
    for a,b in zip(base, scaled):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6), f"Mismatch with scaling: {a} vs {b}"
