"""Economic and reporting metrics for fermentation ENMPC."""
from __future__ import annotations
from typing import Dict
import pyomo.environ as pe

ECONOMIC_WEIGHTS = {
    'yeast_initial': 50.0,   # coefficient multiplying initial yeast mass (kg)
    'ethanol_penalty': 5.0,  # penalty per (ethanol_conc_final * hold_up_final)
}

def compute_economic_metric(m: pe.ConcreteModel) -> float:
    """Replicates legacy economic objective: 50*Yeast0 - 5*Eth_final_conc * M_final.

    Assumptions:
    - Yeast mass approximated by initial Cell concentration * initial hold-up / 1000 (since C in g/kg => kg/kg *1000 factor)
    - Eth_final_conc = C[t_last,'Eth'] (g/kg)
    - M_final = M[t_last] (kg)
    - If enable_mass_balance not active, returns 0.0 (not meaningful in skeleton mode).
    """
    if not hasattr(m, 'M') or not hasattr(m, 'C'):
        return 0.0
    t0 = m.t.first()
    tL = m.t.last()
    try:
        # Cell conc g/kg -> kg/kg = conc/1000 ; multiply by initial M (kg) -> kg yeast
        cell0 = pe.value(m.C[t0, 'Cell']) if ('Cell' in m.j) else 0.0
        M0 = pe.value(m.M[t0]) if hasattr(m, 'M') else 0.0
        yeast_mass_initial = (cell0/1000.0)*M0
        eth_final_conc = pe.value(m.C[tL, 'Eth']) if ('Eth' in m.j) else 0.0
        M_final = pe.value(m.M[tL]) if hasattr(m, 'M') else 0.0
        metric = ECONOMIC_WEIGHTS['yeast_initial']*yeast_mass_initial - ECONOMIC_WEIGHTS['ethanol_penalty']*eth_final_conc*M_final
        return float(metric)
    except Exception:
        return 0.0

__all__ = [
    'compute_economic_metric',
    'ECONOMIC_WEIGHTS',
]
