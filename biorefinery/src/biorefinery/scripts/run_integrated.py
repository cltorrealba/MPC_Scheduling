"""Integrated demo run: scheduling -> feeds -> fermentation -> economic score.

This is a lightweight illustrative pipeline (not production-grade):
1. Build and solve a minimal scheduling problem.
2. Apply schedule output to fermentation feed composition (Cin) incrementally.
3. Build fermentation model and (optionally) solve / evaluate objective.
4. Compute aggregate economic metric combining ethanol yield and demand fulfillment.

Usage (example):
    python -m biorefinery.scripts.run_integrated --print
Optional flags:
    --no-solve-fermentation   Skip solving fermentation (use initial values).
    --weight-yield 0.7 --weight-demand 0.3  Adjust metric weights.

Note: This script intentionally stays simple to keep runtime small for CI.
"""
from __future__ import annotations
import argparse
import pyomo.environ as pe

from biorefinery.models import (
    TaskDef, UnitDef, SchedulingConfig, build_minimal_scheduling_model
)
from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.integration.scheduling_control_interface import apply_schedule_to_feeds
from biorefinery.metrics.economic_aggregate import compute_economic_aggregate


def run(args):
    # 1. Scheduling
    tasks = [
        TaskDef(name='T_Eth', inputs={}, outputs={'Eth_state': 1.0}, units=['U'], min_batch=5, max_batch=5, process_time_h=1.0)
    ]
    units = [UnitDef(name='U')]
    states = ['Eth_state']
    cfg = SchedulingConfig(
        horizon_h=6.0,
        n_periods=6,
        tasks=tasks,
        units=units,
        states=states,
        initial_inventory={'Eth_state': 0.0},
        storage_capacity={'Eth_state': 1000.0},
        demand={('Eth_state', 5): 5.0}
    )
    sched_res = build_minimal_scheduling_model(cfg)
    m_s = sched_res.model
    # Force a single batch at t=0
    m_s.X['T_Eth','U',0].fix(1); m_s.B['T_Eth','U',0].fix(5)
    for t in m_s.T:
        if t != 0:
            m_s.X['T_Eth','U',t].fix(0); m_s.B['T_Eth','U',t].fix(0)
    solver = pe.SolverFactory('glpk')
    solved = False
    if solver is not None and solver.available(False):
        try:
            solver.solve(m_s, tee=False)
            solved = True
        except Exception:
            solved = False
    if not solved:
        # Fallback: manually propagate inventory based on fixed batch at t=0
        produced = float(m_s.B['T_Eth','U',0].value or 0.0)
        for t in m_s.T:
            try:
                m_s.S['Eth_state', t].set_value(produced)
            except Exception:
                pass

    # Demand fulfillment approximation: inventory at final period
    # Fulfilled demand; safe access even if unsolved
    try:
        fulfilled = float(pe.value(m_s.S['Eth_state', cfg.n_periods - 1]))
    except Exception:
        fulfilled = float(m_s.S['Eth_state', cfg.n_periods - 1].value or 0.0)
    total_demand = 5.0

    # 2. Fermentation model
    m_f = build_fermentation_model(include_kinetics=True, detailed_kinetics=False, enable_mass_balance=True,
                                   initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    # Map scheduling state production to Eth feed species (simplistic example)
    apply_schedule_to_feeds(m_f, m_s, mapping={'Eth_state':'Eth'})

    # 3. Optional solve fermentation
    produced_ethanol_mass = 0.0
    theoretical_max_ethanol = 100.0  # placeholder normalization
    if not args.no_solve_fermentation:
        for cand in ['ipopt','glpk']:
            sf = pe.SolverFactory(cand)
            if sf is not None and sf.available(False):
                try:
                    sf.solve(m_f, tee=False)
                    break
                except Exception:
                    continue
        # Use final concentration * hold-up as proxy mass (g/kg * kg = g)
        t_last = m_f.t.last()
        produced_ethanol_mass = float(pe.value(m_f.C[t_last,'Eth']) * pe.value(m_f.M[t_last]) / 1000.0)
    else:
        # Base on feed increment only (Cin effect minimal in this skeleton)
        try:
            produced_ethanol_mass = float(pe.value(m_f.Cin['Eth']))
        except Exception:
            produced_ethanol_mass = 0.0

    # 4. Economic aggregate
    econ = compute_economic_aggregate(
        produced_ethanol_mass=produced_ethanol_mass,
        theoretical_max_ethanol_mass=theoretical_max_ethanol,
        fulfilled_demand_mass=fulfilled,
        total_demand_mass=total_demand,
        weight_yield=args.weight_yield,
        weight_demand=args.weight_demand,
        meta={'note':'demo'}
    )

    if args.print:
        print('Integrated run result:')
        print('  Produced ethanol mass (proxy):', produced_ethanol_mass)
        print('  Demand fulfilled:', fulfilled)
        print('  Aggregate score:', econ.score)
    return econ


def build_parser():
    p = argparse.ArgumentParser(description='Integrated scheduling + fermentation demo')
    p.add_argument('--no-solve-fermentation', action='store_true', help='Skip solving fermentation model')
    p.add_argument('--weight-yield', type=float, default=0.5)
    p.add_argument('--weight-demand', type=float, default=0.5)
    p.add_argument('--print', action='store_true')
    return p


def main():
    args = build_parser().parse_args()
    run(args)


if __name__ == '__main__':  # pragma: no cover
    main()
