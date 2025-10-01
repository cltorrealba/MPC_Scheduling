"""Persistent DSDA multi-start runner.

Explora configuraciones de activación de rutas cinéticas (G,X,F,HMF,ACT)
usando un esquema multi-start con caché persistente para evitar recalcular
configuraciones ya visitadas.
"""
from __future__ import annotations
import argparse, json, os, time, math, random, hashlib
import pyomo.environ as pe
from biorefinery.models.fermentation import (
    build_fermentation_model,
    set_route_activation,
)

ROUTES = ['G','X','F','HMF','ACT']


def _config_hash(args):
    keys = ['nfe','horizon_h','rate_scale','max_concentration','min_hold_up','detailed']
    payload = {k: getattr(args,k,None) for k in keys}
    raw = json.dumps(payload, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def mask_to_active(mask:int):
    return [r for i,r in enumerate(ROUTES) if (mask >> i) & 1]


def build_and_solve(args, mask:int):
    m = build_fermentation_model(
        n_f_elements_t=args.nfe,
        total_f_elements_t=args.nfe,
        total_sim_time=args.horizon_h*3600.0,
        current_start_time_seconds=0.0,
        include_kinetics=True,
        detailed_kinetics=args.detailed,
        initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0},
        enable_mass_balance=True,
        feed_control=False,
        max_concentration=args.max_concentration,
        min_hold_up=args.min_hold_up,
        rate_scale=args.rate_scale,
    )
    for i,r in enumerate(ROUTES):
        # set_route_activation ensures q fixing semantics
        set_route_activation(m, r, bool((mask>>i)&1))
    solver = pe.SolverFactory('ipopt')
    t0 = time.time()
    try:
        res = solver.solve(m, tee=args.tee)
        status = str(res.solver.termination_condition)
    except Exception as e:
        status = f"error:{e.__class__.__name__}"
    solve_time = time.time() - t0
    try:
        obj_val = float(pe.value(m.obj))
    except Exception:
        obj_val = math.nan
    try:
        Eth_final = float(pe.value(m.C[m.t.last(),'Eth']))
    except Exception:
        Eth_final = math.nan
    return {
        'mask': mask,
        'active_routes': mask_to_active(mask),
        'objective': obj_val,
        'ethanol_final': Eth_final,
        'status': status,
        'solve_time_s': solve_time,
    }


def load_cache(path):
    if not path or not os.path.exists(path):
        return None
    with open(path,'r',encoding='utf-8') as f:
        return json.load(f)


def save_cache(path, payload):
    tmp = path + '.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(payload,f,indent=2)
    os.replace(tmp,path)


def parse_args():
    p = argparse.ArgumentParser(description='DSDA multi-start persistent exploration')
    p.add_argument('--nfe', type=int, default=2)
    p.add_argument('--horizon-h', type=float, default=12.0)
    p.add_argument('--starts', type=int, default=20, help='Número de configuraciones nuevas a intentar')
    p.add_argument('--cache', default='dsda_cache.json')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--detailed', action='store_true')
    p.add_argument('--rate-scale', type=float, default=10.0)
    p.add_argument('--max-concentration', type=float, default=200.0)
    p.add_argument('--min-hold-up', type=float, default=100.0)
    p.add_argument('--exhaustive', action='store_true', help='Evalúa todas las combinaciones (2^5=32)')
    p.add_argument('--tee', action='store_true')
    return p.parse_args()


def pick_new_masks(existing_masks:set[int], n:int):
    universe = [m for m in range(0, 1<<len(ROUTES)) if m not in existing_masks]
    if not universe:
        return []
    random.shuffle(universe)
    return universe[:n]


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    cfg_hash = _config_hash(args)
    cache = load_cache(args.cache)
    entries = []
    if cache and cache.get('config_hash') == cfg_hash:
        entries = cache.get('entries', [])
    existing_masks = {e['mask'] for e in entries}
    if args.exhaustive:
        new_masks = [m for m in range(0, 1<<len(ROUTES)) if m not in existing_masks]
    else:
        new_masks = pick_new_masks(existing_masks, args.starts)

    for mask in new_masks:
        result = build_and_solve(args, mask)
        entries.append(result)
        save_cache(args.cache, {
            'config_hash': cfg_hash,
            'routes': ROUTES,
            'entries': entries,
            'best': min((e for e in entries if math.isfinite(e.get('objective', math.nan))), key=lambda x: x['objective'], default=None)
        })

    out = {
        'config_hash': cfg_hash,
        'routes': ROUTES,
        'entries': entries,
        'best': min((e for e in entries if math.isfinite(e.get('objective', math.nan))), key=lambda x: x['objective'], default=None)
    }
    print(json.dumps(out, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
