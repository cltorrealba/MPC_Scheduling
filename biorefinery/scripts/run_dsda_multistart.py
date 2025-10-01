"""Persistent DSDA multi-start runner.

Explora configuraciones de activación de rutas cinéticas (G,X,F,HMF,ACT) usando
un esquema multi-start con caché persistente para evitar re-solver estados ya
visitados.

Bitmask rutas (orden fijo):
  bit0 -> G
  bit1 -> X
  bit2 -> F
  bit3 -> HMF
  bit4 -> ACT

Almacena resultados en JSON con:
- config_hash (parámetros claves de construcción)
- entries: lista de {mask, active_routes, objective, status, solve_time_s}
- best: entrada con menor valor de objetivo (recordatorio: objetivo interno es minimizar -Eth => menor => mayor Eth)

Uso básico:
  python -m biorefinery.scripts.run_dsda_multistart --nfe 2 --horizon-h 12 --starts 10 --cache dsda_cache.json

"""
from __future__ import annotations
import argparse, json, os, time, math, random, hashlib
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation, get_route_external_variables

ROUTES = ['G','X','F','HMF','ACT']


def _config_hash(args):
    keys = ['nfe','horizon_h','rate_scale','max_concentration','min_hold_up']
    payload = {k: getattr(args,k,None) for k in keys}
    raw = json.dumps(payload, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]

def mask_to_active(mask:int):
    return [r for i,r in enumerate(ROUTES) if (mask >> i) & 1]


def active_to_mask(active):
    mask = 0
    for i,r in enumerate(ROUTES):
        if r in active:
            mask |= (1 << i)
    return mask


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
    # Activar rutas según bitmask
    for i,r in enumerate(ROUTES):
        set_route_activation(m, r, bool((mask>>i)&1))
    # Objetivo ya está creado (maximiza Eth => minimize -Eth). Resolver.
    solver = pe.SolverFactory('ipopt')
    t0 = time.time()
    try:
        res = solver.solve(m, tee=False)
        status = str(res.solver.termination_condition)
    except Exception as e:
        status = f"error:{e.__class__.__name__}"
    solve_time = time.time() - t0
    try:
        # objective value (note Pyomo stored as minimization of -Eth)
        obj_val = float(pe.value(m.obj))
    except Exception:
        obj_val = math.nan
    # Extract ethanol final for convenience
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
    p.add_argument('--starts', type=int, default=20, help='Número de configuraciones nuevas a intentar (si cache no las contiene)')
    p.add_argument('--cache', default='dsda_cache.json')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--detailed', action='store_true')
    p.add_argument('--rate-scale', type=float, default=10.0)
    p.add_argument('--max-concentration', type=float, default=200.0)
    p.add_argument('--min-hold-up', type=float, default=100.0)
    p.add_argument('--exhaustive', action='store_true', help='Ignora --starts y evalúa todas las combinaciones (2^5=32)')
    p.add_argument('--tee', action='store_true')
    return p.parse_args()


def pick_new_masks(existing_masks:set[int], n:int):
    # Random uniform over all 0..31 excluding existing
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
    elif cache and cache.get('config_hash') != cfg_hash:
        # Config cambió: mantenemos histórico pero no mezclamos
        entries = []
    existing_masks = {e['mask'] for e in entries}

    # Exhaustivo vs aleatorio
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
