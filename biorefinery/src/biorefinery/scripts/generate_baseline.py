import os
import json
import argparse
import hashlib
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation
from biorefinery.optimization.solvers import pick_available_solver

DEFAULT_BASELINE = 'tests/validation_baseline_fermentation.json'
"""Baseline generation script (multi-species extended).

Now tracks additional inhibitory / byproduct species (F, HMF, ACT) so
regression covers more kinetics routes. Adds an adaptive small-value
series tolerance (tolerance_abs_series_small) applied when |ref| < small
threshold (1e-3) to avoid over-penalizing near-zero noise while still
capturing drift on larger magnitudes.
"""

# Extended species list (legacy subset + inhibitors / acetate)
TRACK_SPECIES = ['G','X','Eth','Cell','CO2','F','HMF','ACT']

# Final metric tolerances
ABS_TOL_FINAL = 1e-5
REL_TOL_FINAL = 1e-3

# Series tolerances (dual): absolute, relative; plus stricter small-value abs tol
ABS_TOL_SERIES = 1e-4
REL_TOL_SERIES = 2e-3
ABS_TOL_SERIES_SMALL = 5e-5  # applied when |ref| < 1e-3

# Flags por defecto para incluir series de tasas
INCLUDE_Q_SERIES = True
INCLUDE_R_SERIES = True

INIT = { 'G':10.0,'X':5.0,'Eth':0.0,'Cell':1.0,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0 }


def build_and_solve(solver_name=None, detailed=True):
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=detailed,
                                 initial_concentrations=INIT)
    for r in ['G','X','F','HMF','ACT']:
        set_route_activation(m, r, True)
    if solver_name is None:
        solver_name, _ = pick_available_solver(return_options=True)
    if solver_name is None:
        raise RuntimeError('No solver disponible para generar baseline')
    sf = pe.SolverFactory(solver_name)
    if not (sf and sf.available(False)):
        raise RuntimeError(f'Solver {solver_name} no disponible')
    sf.solve(m, tee=False)
    return m, solver_name


def _collect_param_hash(model):
    data = {}
    for p in model.component_objects(pe.Param, descend_into=True):
        name = p.getname()
        if name in {'final_time', 'current_starting_time', 'current_final_time'}:
            continue
        try:
            items = []
            for idx in p:
                try:
                    items.append(float(pe.value(p[idx])))
                except Exception:
                    continue
            if not items and not p.is_indexed():
                try:
                    items = [float(pe.value(p.value))]
                except Exception:
                    continue
            if items:
                data[name] = items
        except Exception:
            continue
    flat = []
    for k in sorted(data.keys()):
        flat.append(k)
        flat.extend(data[k])
    raw = json.dumps(flat, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def extract_payload(m, solver_name, include_q=True, include_r=True):
    time_points = [float(t)*pe.value(m.final_time) for t in m.t]
    series = {sp: [pe.value(m.C[t, sp]) for t in m.t] for sp in TRACK_SPECIES}
    metrics = {
        'obj': pe.value(m.obj),
        'G_final': pe.value(m.C[m.t.last(),'G']),
        'X_final': pe.value(m.C[m.t.last(),'X']),
        'Eth_final': pe.value(m.C[m.t.last(),'Eth']),
        'Cell_final': pe.value(m.C[m.t.last(),'Cell']),
        'CO2_final': pe.value(m.C[m.t.last(),'CO2']),
    }
    q_series = {}
    if include_q and hasattr(m, 'q'):
        for s in m.kinetic_species:
            q_series[s] = [pe.value(m.q[t, s]) for t in m.t]
    R_series = {}
    if include_r and hasattr(m, 'R'):
        for r in m.product_reactions:
            R_series[r] = [pe.value(m.R[t, r]) for t in m.t]
    payload = {
        'metrics': metrics,
        'tolerance_abs_final': ABS_TOL_FINAL,
        'tolerance_rel_final': REL_TOL_FINAL,
        'tolerance_abs_series': ABS_TOL_SERIES,
        'tolerance_rel_series': REL_TOL_SERIES,
        'species': TRACK_SPECIES,
        'time': time_points,
        'series': series,
        'solver': solver_name,
        'param_hash': _collect_param_hash(m),
        'tolerance_abs_series_small': ABS_TOL_SERIES_SMALL,
        'adaptive_small_threshold': 1e-3,
    }
    if q_series:
        payload['q_series'] = q_series
    if R_series:
        payload['R_series'] = R_series
    return payload


def main():
    parser = argparse.ArgumentParser(description='Generar (o regenerar) baseline de fermentación')
    parser.add_argument('--output', default=DEFAULT_BASELINE, help='Ruta archivo baseline JSON')
    parser.add_argument('--solver', default=None, help='Forzar solver (ipopt, bonmin, etc.)')
    parser.add_argument('--force', action='store_true', help='Sobrescribir si existe')
    parser.add_argument('--no-detailed', action='store_true', help='Usar cinética simplificada')
    parser.add_argument('--no-rates', action='store_true', help='No incluir series de tasas (q_series, R_series)')
    args = parser.parse_args()

    if os.path.exists(args.output) and not args.force:
        print('Archivo baseline ya existe. Use --force para sobrescribir.')
        return 0

    m, solver_name = build_and_solve(solver_name=args.solver, detailed=not args.no_detailed)
    include_rates = not args.no_rates
    payload = extract_payload(m, solver_name,
                              include_q=include_rates and INCLUDE_Q_SERIES,
                              include_r=include_rates and INCLUDE_R_SERIES)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output,'w',encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    print(f'Baseline guardada en {args.output} con solver={solver_name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
