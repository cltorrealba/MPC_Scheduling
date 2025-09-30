import json
import math
import os
import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation

BASELINE_FILE = 'tests/validation_baseline_fermentation.json'

@pytest.mark.skipif(not os.path.exists(BASELINE_FILE), reason='Baseline no encontrada')
def test_timeseries_only():
    with open(BASELINE_FILE,'r',encoding='utf-8') as f:
        baseline = json.load(f)
    species = baseline['species']
    time_ref = baseline['time']
    series_ref = baseline['series']
    solver_name = baseline.get('solver','ipopt')
    q_ref = baseline.get('q_series', {})
    R_ref = baseline.get('R_series', {})

    # Reconstuir modelo con misma configuración
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
                                 initial_concentrations={ 'G':10.0,'X':5.0,'Eth':0.0,'Cell':1.0,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0 })
    for r in ['G','X','F','HMF','ACT']:
        set_route_activation(m, r, True)

    sf = pe.SolverFactory(solver_name)
    if not (sf and sf.available(False)):
        pytest.skip(f'Solver {solver_name} no disponible para validación')
    sf.solve(m, tee=False)

    # Extraer series actuales
    current_time = [float(t)*pe.value(m.final_time) for t in m.t]
    assert len(current_time) == len(time_ref), 'Longitud tiempo difiere'

    abs_series = baseline.get('tolerance_abs_series', 1e-4)
    rel_series = baseline.get('tolerance_rel_series', 2e-3)

    for sp in species:
        cur_vals = [pe.value(m.C[t, sp]) for t in m.t]
        ref_vals = series_ref[sp]
        assert len(cur_vals) == len(ref_vals)
        for idx,(cv, rv) in enumerate(zip(cur_vals, ref_vals)):
            diff = abs(cv - rv)
            rel = diff / max(1e-12, abs(rv))
            if not (diff <= abs_series or rel <= rel_series):
                raise AssertionError(f'Serie {sp}[{idx}] diff={diff} rel={rel} fuera de tolerancia')

    # Validación estructural de series de tasas si existen en baseline
    if q_ref:
        assert hasattr(m, 'q'), 'Modelo no tiene componente q pero baseline sí'
        for s, ref_vals in q_ref.items():
            cur_vals = [pe.value(m.q[t, s]) for t in m.t]
            assert len(cur_vals) == len(ref_vals), f'Longitud q_series {s} difiere'
    if R_ref:
        assert hasattr(m, 'R'), 'Modelo no tiene componente R pero baseline sí'
        for r, ref_vals in R_ref.items():
            cur_vals = [pe.value(m.R[t, r]) for t in m.t]
            assert len(cur_vals) == len(ref_vals), f'Longitud R_series {r} difiere'
