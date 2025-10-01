import json
import os
import argparse
import pyomo.environ as pe
from pathlib import Path

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.legacy.param_hash import compute_param_hash
from biorefinery.legacy.baseline_manager import (
    load_baseline, save_baseline,
    SECTION_DYNAMIC, SECTION_SERIES, SECTION_RATES,
    set_param_hash, GLOBAL_PARAM_HASH_KEY
)
from biorefinery.legacy.tolerances import dynamic_tolerances, series_tolerances, rates_tolerances


def pick_solver():
    for name in ("ipopt","glpk","bonmin"):
        try:
            sf = pe.SolverFactory(name)
            if sf and sf.available(False):
                return name
        except Exception:
            continue
    return None


def build_models(nfe_dyn:int, nfe_series:int, nfe_rates:int):
    # All share same discretization for simplicity now; could diverge later if needed
    kwargs = dict(include_kinetics=True, detailed_kinetics=False,
                  initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    m_dyn = build_fermentation_model(n_f_elements_t=nfe_dyn, total_f_elements_t=nfe_dyn, **kwargs)
    m_series = build_fermentation_model(n_f_elements_t=nfe_series, total_f_elements_t=nfe_series, **kwargs)
    m_rates = build_fermentation_model(n_f_elements_t=nfe_rates, total_f_elements_t=nfe_rates, **kwargs)
    # Initialize q/R at first timepoint to zero (avoid uninitialized var evaluation warnings)
    for m in (m_dyn, m_series, m_rates):
        if hasattr(m, 'q'):
            t0 = m.t.first()
            for sp in m.kinetic_species:
                if (t0, sp) in m.q and m.q[t0, sp].value is None:
                    m.q[t0, sp].set_value(0.0)
        if hasattr(m, 'R'):
            t0 = m.t.first()
            for rx in m.product_reactions:
                if (t0, rx) in m.R and m.R[t0, rx].value is None:
                    m.R[t0, rx].set_value(0.0)
    return m_dyn, m_series, m_rates


def solve(model, solver_name):
    solver = pe.SolverFactory(solver_name)
    res = solver.solve(model, tee=False)
    try:
        term = str(res.solver.termination_condition)
    except Exception:
        term = 'unknown'
    return term


def extract_finals(model, species):
    tL = model.t.last()
    out = {}
    for sp in species:
        if (tL, sp) in model.C:
            try:
                out[sp] = float(pe.value(model.C[tL, sp]))
            except Exception:
                pass
    return out


def extract_series(model, species):
    tlist = sorted(list(model.t))
    times = [float(t) for t in tlist]
    data = {sp: [] for sp in species}
    for t in tlist:
        for sp in species:
            try:
                data[sp].append(float(pe.value(model.C[t, sp])))
            except Exception:
                data[sp].append(None)
    return times, data


def extract_rates(model):
    tlist = sorted(list(model.t))
    times = [float(t) for t in tlist]
    q_series = {}
    R_series = {}
    if hasattr(model, 'q'):
        for _, sp in model.q:
            q_series.setdefault(sp, [])
        for t in tlist:
            for _, sp in model.q:
                val = model.q[t, sp].value if (t, sp) in model.q else None
                q_series[sp].append(None if val is None else float(val))
    if hasattr(model, 'R'):
        for _, rx in model.R:
            R_series.setdefault(rx, [])
        for t in tlist:
            for _, rx in model.R:
                val = model.R[t, rx].value if (t, rx) in model.R else None
                R_series[rx].append(None if val is None else float(val))
    return times, q_series, R_series


def main():
    ap = argparse.ArgumentParser(description='Generate unified legacy equivalence baseline JSON')
    ap.add_argument('--output', default='tests/legacy_unified_baseline.json')
    ap.add_argument('--nfe', type=int, default=4, help='Finite elements for series & rates models')
    ap.add_argument('--nfe-dynamic', type=int, default=3, help='Finite elements for dynamic finals model')
    ap.add_argument('--refresh', action='store_true', help='Force overwrite sections & param hash')
    ap.add_argument('--feasible-seed', action='store_true', help='Skip solver; produce trivial steady baseline (q=R=0, concentrations constant)')
    ap.add_argument('--no-solver', action='store_true', help='Alias for --feasible-seed')
    ap.add_argument('--fallback-if-infeasible', action='store_true', help='Attempt solve; if termination indicates infeasible then replace values with feasible seed for that model and mark status feasible_seed_fallback')
    ap.add_argument('--diagnose', action='store_true', help='Print top constraint violations pre/post solve and on fallback')
    args = ap.parse_args()

    solver_name = pick_solver()
    # alias handling
    if args.no_solver:
        args.feasible_seed = True

    if solver_name is None and not args.feasible_seed:
        print('No solver available and not in feasible-seed mode; aborting baseline generation')
        return 1

    m_dyn, m_series, m_rates = build_models(args.nfe_dynamic, args.nfe, args.nfe)
    # Track fallback usage per model
    fallback_used = {'dynamic': False, 'series': False, 'rates': False}

    if args.feasible_seed:
        # Populate trivial steady state: leave initial concentrations as given; force derivatives zero.
        status_dyn = status_series = status_rates = 'feasible_seed'
        for m in (m_dyn, m_series, m_rates):
            t0 = m.t.first()
            tL = m.t.last()
            # Fix all concentrations at their initial value for all time points
            for t in m.t:
                for sp in m.j:
                    if (t0, sp) in m.C and m.C[t0, sp].fixed:
                        base = m.C[t0, sp].value
                        if (t, sp) in m.C and t != t0:
                            m.C[t, sp].fix(base)
            # Zero rates
            if hasattr(m, 'q'):
                for idx in m.q:
                    m.q[idx].fix(0.0)
            if hasattr(m, 'R'):
                for idx in m.R:
                    m.R[idx].fix(0.0)
            # Derivatives implicitly zero since values constant; dCdt Var may exist but Pyomo value unused.
    else:
        if args.diagnose:
            try:
                from biorefinery.models.model_diagnostics import print_diagnostics
                print_diagnostics(m_dyn, header='[dynamic] pre-solve violations')
                print_diagnostics(m_series, header='[series] pre-solve violations')
                print_diagnostics(m_rates, header='[rates] pre-solve violations')
            except Exception as e:
                print(f"[diagnostics] pre-solve import error: {e}")
        status_dyn = solve(m_dyn, solver_name)
        status_series = solve(m_series, solver_name)
        status_rates = solve(m_rates, solver_name)
        if args.diagnose:
            try:
                from biorefinery.models.model_diagnostics import print_diagnostics
                print_diagnostics(m_dyn, header=f'[dynamic] post-solve status={status_dyn}')
                print_diagnostics(m_series, header=f'[series] post-solve status={status_series}')
                print_diagnostics(m_rates, header=f'[rates] post-solve status={status_rates}')
            except Exception as e:
                print(f"[diagnostics] post-solve import error: {e}")

        if args.fallback_if_infeasible:
            # Evaluate each status; if infeasible fallback to feasible seed values for that model
            model_triplets = [ ('dynamic', m_dyn, status_dyn), ('series', m_series, status_series), ('rates', m_rates, status_rates) ]
            for label, model, status in model_triplets:
                if status and 'infeasible' in status.lower():
                    fallback_used[label] = True
                    if args.diagnose:
                        try:
                            from biorefinery.models.model_diagnostics import print_diagnostics
                            print_diagnostics(model, header=f'[{label}] violations triggering fallback')
                        except Exception as e:
                            print(f"[diagnostics] fallback import error: {e}")
                    t0 = model.t.first()
                    for t in model.t:
                        for sp in model.j:
                            if (t0, sp) in model.C and model.C[t0, sp].value is not None:
                                if (t, sp) in model.C and t != t0:
                                    model.C[t, sp].fix(model.C[t0, sp].value)
                    if hasattr(model, 'q'):
                        for idx in model.q:
                            model.q[idx].fix(0.0)
                    if hasattr(model, 'R'):
                        for idx in model.R:
                            model.R[idx].fix(0.0)
            if fallback_used['dynamic']:
                status_dyn = 'feasible_seed_fallback'
            if fallback_used['series']:
                status_series = 'feasible_seed_fallback'
            if fallback_used['rates']:
                status_rates = 'feasible_seed_fallback'

    phash = compute_param_hash(m_dyn)
    if not args.feasible_seed and not args.fallback_if_infeasible:
        for label, status in [('dynamic', status_dyn), ('series', status_series), ('rates', status_rates)]:
            if status and 'infeasible' in status.lower():
                print(f"[WARN] {label} model termination status indicates infeasible: {status}")

    dyn_tol = dynamic_tolerances()
    finals_new = extract_finals(m_dyn, ['G','X','Eth','Cell'])
    # Legacy finals not computed here (would require legacy build); store only new for structural tracking

    series_tol = series_tolerances()
    t_series, series_new = extract_series(m_series, ['G','X','Eth'])

    rates_tol = rates_tolerances()
    t_rates, q_ser, R_ser = extract_rates(m_rates)

    baseline = load_baseline() if not args.refresh else {}

    # Decide solver label for output clarity
    solver_label = solver_name
    if args.feasible_seed:
        solver_label = 'feasible_seed'
    elif args.fallback_if_infeasible and any(fallback_used.values()):
        solver_label = f"{solver_name}+fallback"

    baseline[SECTION_DYNAMIC] = {
        'solver': solver_label,
        'status': status_dyn,
        'finals_new': finals_new,
        'species': ['G','X','Eth','Cell'],
        'abs_tol': dyn_tol.abs_tol,
        'rel_tol': dyn_tol.rel_tol,
        'param_hash': phash,
    }
    baseline[SECTION_SERIES] = {
        'solver': solver_label,
        'status': status_series,
        'time': t_series,
        'series_new': series_new,
        'species': ['G','X','Eth'],
        'abs_tol': series_tol.abs_tol,
        'rel_tol': series_tol.rel_tol,
        'param_hash': phash,
    }
    baseline[SECTION_RATES] = {
        'solver': solver_label,
        'status': status_rates,
        'time': t_rates,
        'q_series_new': q_ser,
        'R_series_new': R_ser,
        'abs_tol': rates_tol.abs_tol,
        'rel_tol': rates_tol.rel_tol,
        'param_hash': phash,
    }
    baseline[GLOBAL_PARAM_HASH_KEY] = phash

    save_baseline(baseline)
    print(f"Unified baseline written to {args.output} (solver={solver_label}, param_hash={phash})")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
