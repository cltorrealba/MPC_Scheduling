import json
import math
import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation

SOLVER_CANDIDATES = [
    ('ipopt', {}),
    ('gams', {'solver': 'conopt'}),  # GAMS con CONOPT si licencia disponible
    ('bonmin', {}),
    ('couenne', {}),
    ('scip', {}),
    ('highs', {}),
]

def pick_solver():
    for name, opts in SOLVER_CANDIDATES:
        try:
            sf = pe.SolverFactory(name)
            if not sf.available(False):
                continue
            # Para gams con subsolver, guardar opción
            return name, opts
        except Exception:
            continue
    return None, None

solver_name, solver_options = pick_solver()

BASELINE_FILE = 'tests/validation_baseline_fermentation.json'
ABS_TOL_FINAL = 1e-5
REL_TOL_FINAL = 1e-3
ABS_TOL_SERIES = 1e-4
REL_TOL_SERIES = 2e-3
TRACK_SPECIES = ['G','X','Eth','Cell','CO2']
RATE_INCLUDE_Q = True
RATE_INCLUDE_R = True

BASE_INIT = {
    'G': 10.0,
    'X': 5.0,
    'Eth': 0.0,
    'Cell': 1.0,
    'F': 0.2,
    'HMF': 0.1,
    'ACT': 0.05,
    'CO2': 0.0,
}

@pytest.mark.skipif(solver_name is None, reason='Ningún solver candidato disponible')
def test_generate_or_validate_baseline(tmp_path):
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
                                 initial_concentrations=BASE_INIT)
    # Asegurar todas las rutas activas
    for r in ['G','X','F','HMF','ACT']:
        set_route_activation(m, r, True)
    solver = pe.SolverFactory(solver_name)
    # Aplicar opciones (e.g. gams->conopt)
    if solver_options:
        for k, v in solver_options.items():
            solver.options[k] = v
    solver.solve(m, tee=False)

    metrics = {
        'obj': pe.value(m.obj),
        'G_final': pe.value(m.C[m.t.last(),'G']),
        'X_final': pe.value(m.C[m.t.last(),'X']),
        'Eth_final': pe.value(m.C[m.t.last(),'Eth']),
        'Cell_final': pe.value(m.C[m.t.last(),'Cell']),
        'CO2_final': pe.value(m.C[m.t.last(),'CO2']),
    }
    # Construir series
    time_points = []
    series = {sp: [] for sp in TRACK_SPECIES}
    q_series = {}
    R_series = {}
    if hasattr(m, 'q') and RATE_INCLUDE_Q:
        for s in m.kinetic_species:
            q_series[s] = []
    if hasattr(m, 'R') and RATE_INCLUDE_R:
        for r in m.product_reactions:
            R_series[r] = []
    # Escalar tiempo físico: t in [0,1] -> actual usando final_time
    def _safe_val(x):
        try:
            v = pe.value(x)
        except Exception:
            return 0.0
        return 0.0 if v is None else v
    for t in m.t:
        time_points.append(float(t) * pe.value(m.final_time))
        for sp in TRACK_SPECIES:
            series[sp].append(pe.value(m.C[t, sp]))
        if q_series:
            for s in q_series.keys():
                q_series[s].append(_safe_val(m.q[t, s]))
        if R_series:
            for r in R_series.keys():
                R_series[r].append(_safe_val(m.R[t, r]))

    # Calcular hash de parámetros cinéticos principales
    import hashlib
    def _collect_param_data(model):
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
        # Orden determinístico
        flat = []
        for k in sorted(data.keys()):
            flat.append(k)
            flat.extend(data[k])
        raw = json.dumps(flat, separators=(',', ':'), ensure_ascii=True)
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()
    param_hash = _collect_param_data(m)

    # Si no existe baseline, crearla (primera ejecución controlada)
    import os
    import os
    refresh = os.getenv('BIOREF_REFRESH_BASELINE', '0') == '1'
    if (not os.path.exists(BASELINE_FILE)) or refresh:
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
            'q_series': q_series,
            'R_series': R_series,
            'param_hash': param_hash,
        }
        with open(BASELINE_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        msg = 'Baseline regenerada' if refresh else 'Baseline creada'
        pytest.skip(f'{msg} con solver={solver_name}; re-ejecutar prueba para validar')

    with open(BASELINE_FILE, 'r', encoding='utf-8') as f:
        stored = json.load(f)
    # Migración baseline legado: si no existen series, regenerar payload completo y hacer skip informativo
    if 'series' not in stored or 'time' not in stored or 'species' not in stored:
        # Construir payload nuevo basado en ejecución actual
        new_payload = {
            'metrics': metrics,
            'tolerance_abs_final': ABS_TOL_FINAL,
            'tolerance_rel_final': REL_TOL_FINAL,
            'tolerance_abs_series': ABS_TOL_SERIES,
            'tolerance_rel_series': REL_TOL_SERIES,
            'species': TRACK_SPECIES,
            'time': time_points,
            'series': series,
            'solver': solver_name,
            'q_series': q_series,
            'R_series': R_series,
            'param_hash': param_hash,
            'upgraded_from_legacy': True,
        }
        with open(BASELINE_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_payload, f, indent=2)
        pytest.skip('Baseline legacy actualizada para incluir series; re-ejecutar prueba')
    baseline_solver = stored.get('solver', solver_name)
    if baseline_solver != solver_name:
        pytest.skip(f'Solver baseline={baseline_solver} != actual={solver_name}; use BIOREF_REFRESH_BASELINE=1 para regenerar')
    stored_hash = stored.get('param_hash')
    if stored_hash and stored_hash != param_hash and not refresh:
        pytest.skip('Hash de parámetros difiere; regenerar baseline (BIOREF_REFRESH_BASELINE=1) si el cambio es esperado')
    abs_final = stored.get('tolerance_abs_final', ABS_TOL_FINAL)
    rel_final = stored.get('tolerance_rel_final', REL_TOL_FINAL)
    # Validación métricas finales (dual tolerancia)
    for k, v in metrics.items():
        assert math.isfinite(v), f'Metric {k} no finita'
        ref = stored['metrics'][k]
        diff = abs(v - ref)
        rel = diff / max(1e-12, abs(ref))
        assert (diff <= abs_final) or (rel <= rel_final), f'{k}: diff={diff} rel={rel} fuera de tolerancia'

    # Validación de series
    abs_series = stored.get('tolerance_abs_series', ABS_TOL_SERIES)
    rel_series = stored.get('tolerance_rel_series', REL_TOL_SERIES)
    stored_series = stored.get('series', {})
    for sp in TRACK_SPECIES:
        assert sp in stored_series, f'Serie {sp} no encontrada en baseline'
        ref_list = stored_series[sp]
        cur_list = series[sp]
        assert len(ref_list) == len(cur_list), f'Longitud serie {sp} difiere'
        for idx, (rv, cv) in enumerate(zip(ref_list, cur_list)):
            diff = abs(rv - cv)
            rel = diff / max(1e-12, abs(rv))
            if not (diff <= abs_series or rel <= rel_series):
                raise AssertionError(f'Serie {sp}[{idx}] diff={diff} rel={rel} fuera de tolerancia')

    # Validación mínima de series de tasas si existen
    stored_q = stored.get('q_series', {})
    for s, vals in stored_q.items():
        assert s in q_series, f'q_series faltante {s}'
        assert len(vals) == len(q_series[s])
    stored_R = stored.get('R_series', {})
    for r, vals in stored_R.items():
        assert r in R_series, f'R_series faltante {r}'
        assert len(vals) == len(R_series[r])
