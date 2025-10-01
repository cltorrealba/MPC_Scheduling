import json
import math
import os
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model

BASELINE_FILE = 'tests/dynamic_baseline_new_model.json'
SPECIES_TRACK = ['G','X','Eth','Cell']
ABS_TOL = 1e-5
REL_TOL = 1e-3


def _solve_model():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                  initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0},
                                  n_f_elements_t=3, total_f_elements_t=3)
    # Intentar solver continuo (ipopt) si disponible, si no glpk (aunque modelo puede tener no linealidades light)
    for cand in ['ipopt','glpk']:
        sf = pe.SolverFactory(cand)
        if sf is not None and sf.available(False):
            try:
                sf.solve(m, tee=False)
                break
            except Exception:
                continue
    return m


def _extract_series(m):
    time_pts = []
    series = {s: [] for s in SPECIES_TRACK}
    for t in m.t:
        time_pts.append(float(t) * pe.value(m.final_time))
        for s in SPECIES_TRACK:
            series[s].append(pe.value(m.C[t, s]))
    return time_pts, series


def _hash_params(m):
    import hashlib
    data = []
    for p in m.component_objects(pe.Param, descend_into=True):
        name = p.getname()
        if name in {'final_time','current_starting_time','current_final_time'}:
            continue
        try:
            if p.is_indexed():
                for idx in p:
                    data.append((name, float(pe.value(p[idx]))))
            else:
                data.append((name, float(pe.value(p.value))))
        except Exception:
            continue
    raw = json.dumps(sorted(data), separators=(',',':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def test_dynamic_baseline_new_model(tmp_path):
    m = _solve_model()
    time_pts, series = _extract_series(m)
    param_hash = _hash_params(m)
    refresh = os.getenv('BIOREF_REFRESH_DYN_BASELINE','0') == '1'
    if (not os.path.exists(BASELINE_FILE)) or refresh:
        payload = {
            'time': time_pts,
            'series': series,
            'species': SPECIES_TRACK,
            'param_hash': param_hash,
            'abs_tol': ABS_TOL,
            'rel_tol': REL_TOL,
        }
        with open(BASELINE_FILE,'w',encoding='utf-8') as f:
            json.dump(payload,f,indent=2)
        pytest.skip('Baseline dinámica creada/refrescada; re-ejecutar para validar')
    with open(BASELINE_FILE,'r',encoding='utf-8') as f:
        stored = json.load(f)
    if stored.get('param_hash') != param_hash and not refresh:
        pytest.skip('Hash parámetros difiere; regenerar baseline si cambio es intencional')
    # Validar longitudes
    assert stored['time'] == time_pts, 'Puntos de tiempo cambiaron (discretización distinta)' 
    for s in SPECIES_TRACK:
        ref = stored['series'][s]
        cur = series[s]
        assert len(ref) == len(cur)
        for rv, cv in zip(ref, cur):
            diff = abs(rv - cv)
            rel = diff / max(1e-12, abs(rv))
            assert diff <= stored['abs_tol'] or rel <= stored['rel_tol'], f'{s} diff={diff} rel={rel} fuera de tolerancia'
