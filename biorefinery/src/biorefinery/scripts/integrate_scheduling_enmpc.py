"""Prototype integration script: minimal scheduling -> fermentation model (single horizon).

Workflow:
 1. Build & solve minimal scheduling model.
 2. Aggregate production of selected states over horizon.
 3. Map aggregated production to fermentation feed composition Cin (Param) via simple proportional rule.
 4. Build fermentation model with enable_mass_balance=True and run one solve (Ipopt default) to get ethanol & hold-up results.
 5. Emit a combined JSON payload with scheduling summary, mapping, fermentation KPIs.

This is a first bridge; it intentionally skips:
  * Multi-horizon receding runs (use run_enmpc for full MPC later)
  * Route activation tuning
  * Dynamic repartition of production by time slice
  * Cost harmonization between layers

Usage example:
  python -m biorefinery.scripts.integrate_scheduling_enmpc --output integrated_example.json

Extend mapping logic or scaling factors as domain knowledge refines.
"""
from __future__ import annotations
import json, argparse, math
import pyomo.environ as pe
from biorefinery.models.scheduling_minimal import (
    TaskDef, UnitDef, SchedulingConfig, build_minimal_scheduling_model
)
from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.optimization.solvers import pick_available_solver


def _solve(model, solver_name: str | None = None, tee: bool = False):
    if solver_name is None:
        name, _ = pick_available_solver(return_options=True)
        solver_name = name
    if solver_name is None:
        raise RuntimeError("No solver available")
    sf = pe.SolverFactory(solver_name)
    res = sf.solve(model, tee=tee)
    term = str(res.solver.termination_condition)
    return term, res


def _aggregate_production(m) -> dict:
    """Compute total produced amount per state using rho_prod * B across all tasks/units/periods.
    (rho_cons not netted here; you can subtract consumption later if needed.)"""
    totals = {s: 0.0 for s in m.States}
    for t in m.T:
        for task in m.Tasks:
            for unit in m.Units:
                b = m.B[task, unit, t].value
                if b is None or b <= 0:
                    continue
                for s in m.States:
                    prod = pe.value(m.rho_prod[task, s])
                    cons = pe.value(m.rho_cons[task, s])
                    net = (prod - cons) * b
                    if abs(net) > 0:
                        totals[s] += net
    return totals


def _map_production_to_cin(prod: dict, target_species: list[str], base_scale: float = 1.0, max_conc: float = 200.0) -> dict:
    """Simple mapping: For each target species, compute Cin[sp] = clamp( base_scale * prod[sp], 0, max_conc ).
    If prod lacks a species, defaults to 0. Future improvement: normalization by horizon, density or batch size.
    """
    cin = {}
    for sp in target_species:
        val = prod.get(sp, 0.0) * base_scale
        if math.isnan(val) or val < 0:
            val = 0.0
        cin[sp] = min(max_conc, val)
    return cin


def run_integration(
    args,
    initial_state: dict | None = None,
    start_time_h: float = 0.0,
    capture_fraction: float | None = None,
    previous_batches: dict | None = None,
    fermentation_warm_start: dict | None = None,
    inventory_override: dict | None = None,
):
    # 1. Scheduling toy instance config
    tasks = [
        TaskDef(name="Hydro", inputs={"Cell":0.0}, outputs={"G":0.6, "X":0.3, "ACT":0.05}, units=["U1"], min_batch=10, max_batch=40, process_time_h=1.0),
        TaskDef(name="Detox", inputs={"F":0.1}, outputs={"HMF":0.02, "ACT":0.01}, units=["U1"], min_batch=5, max_batch=20, process_time_h=1.0),
    ]
    units = [UnitDef(name="U1")]
    states = ["G","X","ACT","HMF","F","Cell"]
    base_initial_inventory = {"F":20.0, "Cell":5.0}
    # Extend with zeros for other states
    for s in states:
        base_initial_inventory.setdefault(s, 0.0)
    if inventory_override:
        # Only override known states; ignore others
        applied_override = {k: float(v) for k,v in inventory_override.items() if k in base_initial_inventory}
        initial_inventory_used = {**base_initial_inventory, **applied_override}
    else:
        initial_inventory_used = base_initial_inventory
    cfg = SchedulingConfig(
        horizon_h=args.sched_horizon_h,
        n_periods=args.sched_periods,
        tasks=tasks,
        units=units,
        states=states,
        initial_inventory=initial_inventory_used,
        storage_capacity={s: 1e6 for s in states},
        demand={},
        objective="cost_min",
    )
    sched = build_minimal_scheduling_model(cfg)
    # Warm start scheduling B vars if provided
    if previous_batches:
        for key, val in previous_batches.items():
            try:
                task, unit, period = key.split('|')
                period = int(period)
                if (task, unit, period) in sched.model.B:
                    sched.model.B[task, unit, period].set_value(val)
            except Exception:
                pass
    sched_term, _ = _solve(sched.model, solver_name=args.solver, tee=args.tee)

    # 2. Production aggregation
    prod_net = _aggregate_production(sched.model)

    # 3. Map to Cin species subset for fermentation (only subset relevant to kinetics)
    fer_cin_species = ["G","X","ACT","HMF","F"]
    mapped_cin = _map_production_to_cin(prod_net, fer_cin_species, base_scale=args.cin_scale, max_conc=args.max_concentration)

    # 4. Build & solve fermentation single horizon
    init_conc = {"G":10.0,"X":5.0,"Eth":0.0,"Cell":1.0,"F":0.2,"HMF":0.1,"ACT":0.05,"CO2":0.0}
    # Determine initial concentrations for this horizon
    # If initial_state provided (from previous prediction), use its concentrations (C) overriding defaults
    if initial_state and 'C' in initial_state:
        init_conc_horizon = {**init_conc, **initial_state['C']}
    else:
        init_conc_horizon = init_conc

    mfer = build_fermentation_model(
        n_f_elements_t=args.nfe,
        total_f_elements_t=args.nfe,
        total_sim_time=args.fer_horizon_h*3600.0,
        current_start_time_seconds=start_time_h*3600.0,
        include_kinetics=True,
        detailed_kinetics=False,
        initial_concentrations=init_conc_horizon,
        enable_mass_balance=True,
        feed_control=False,
        max_concentration=args.max_concentration,
        min_hold_up=args.min_hold_up,
        rate_scale=1.0,
    )
    # For subsequent horizons ensure hold-up continuity if provided
    if initial_state and 'M' in initial_state and start_time_h > 0:
        first_t = mfer.t.first()
        try:
            mfer.M[first_t].fix(float(initial_state['M']))
        except Exception:
            pass
    # Fermentation warm start: assign interior points for C and M if provided
    if fermentation_warm_start:
        C_ws = fermentation_warm_start.get('C') or {}
        M_ws = fermentation_warm_start.get('M')
        for tau in mfer.t:
            if tau == mfer.t.first():
                continue  # keep initial fixed
            for sp,val in C_ws.items():
                if (tau, sp) in mfer.C:
                    try:
                        mfer.C[tau, sp].set_value(val)
                    except Exception:
                        pass
            if M_ws is not None:
                try:
                    mfer.M[tau].set_value(M_ws)
                except Exception:
                    pass
    # Inject mapped Cin params
    if hasattr(mfer, 'Cin'):
        for sp, val in mapped_cin.items():
            if sp in mfer.Cin:
                mfer.Cin[sp].set_value(val)
    fer_term, _ = _solve(mfer, solver_name=args.solver, tee=args.tee)

    # Extract KPIs
    def _v(obj, default=None):
        try:
            return float(pe.value(obj))
        except Exception:
            return default
    final_state = {
        'C': {sp: _v(mfer.C[mfer.t.last(), sp]) for sp in mfer.j},
        'M': _v(mfer.M[mfer.t.last()]),
        'abs_final_time_h': start_time_h + args.fer_horizon_h,
    }

    applied_state = None
    if capture_fraction is not None:
        # Select closest discretization point tau in [0,1]
        tau_target = max(0.0, min(1.0, capture_fraction))
        t_points = list(mfer.t)
        # Collocation (ncp=1) points correspond to uniform segmentation; choose nearest
        closest = min(t_points, key=lambda x: abs(float(x) - tau_target))
        applied_state = {
            'C': {sp: _v(mfer.C[closest, sp]) for sp in mfer.j},
            'M': _v(mfer.M[closest]),
            'abs_time_h': start_time_h + tau_target * args.fer_horizon_h,
            'tau_selected': float(closest),
        }
    kpis = {
        'final_ethanol_conc': _v(mfer.C[mfer.t.last(),'Eth']),
        'final_hold_up': _v(mfer.M[mfer.t.last()]),
        'mapped_Cin': {sp: float(val) for sp,val in mapped_cin.items()},
        'prod_net': prod_net,
        'scheduling_status': sched_term,
        'fermentation_status': fer_term,
        'final_state_M': final_state['M'],
    }

    payload = {
        'meta': {
            'sched_horizon_h': args.sched_horizon_h,
            'sched_periods': args.sched_periods,
            'fer_horizon_h': args.fer_horizon_h,
            'nfe': args.nfe,
            'solver': args.solver,
            'cin_scale': args.cin_scale,
            'max_concentration': args.max_concentration,
            'min_hold_up': args.min_hold_up,
        },
        'kpis': kpis,
        'final_state': final_state,
        'applied_state': applied_state,
        'initial_state_echo': initial_state,
        'scheduling': {
            'objective_value': _v(sched.model.obj),
            'batches': {
                f"{task}|{unit}|{t}": _v(sched.model.B[task,unit,t])
                for task in sched.model.Tasks for unit in sched.model.Units for t in sched.model.T
                if _v(sched.model.B[task,unit,t]) not in (None,0)
            },
            'initial_inventory_used': initial_inventory_used,
        }
    }
    if args.output:
        with open(args.output,'w',encoding='utf-8') as f:
            json.dump(payload,f,indent=2)
    return payload


def parse_args():
    p = argparse.ArgumentParser(description="Integrate minimal scheduling with fermentation (single horizon)")
    p.add_argument('--sched-horizon-h', type=float, default=12.0)
    p.add_argument('--sched-periods', type=int, default=6)
    p.add_argument('--fer-horizon-h', type=float, default=12.0)
    p.add_argument('--nfe', type=int, default=2)
    p.add_argument('--solver', default=None)
    p.add_argument('--cin-scale', type=float, default=1.0, help='Multiplicative scale from net production to Cin concentration')
    p.add_argument('--max-concentration', type=float, default=200.0)
    p.add_argument('--min-hold-up', type=float, default=100.0)
    p.add_argument('--output', default='integrated_result.json')
    p.add_argument('--tee', action='store_true')
    return p.parse_args()


def main():
    args = parse_args()
    res = run_integration(args)
    print(json.dumps({'summary': {
        'final_ethanol_conc': res['kpis']['final_ethanol_conc'],
        'final_hold_up': res['kpis']['final_hold_up'],
        'fermentation_status': res['kpis']['fermentation_status'],
        'scheduling_status': res['kpis']['scheduling_status'],
    }}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
