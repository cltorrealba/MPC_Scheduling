import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

# Comparación básica entre legacy y nuevo builder: se enfoca en presencia/consistencia de parámetros clave.
# Ejecuta cinética detallada y revisa que parámetros migrados existan y valores estén dentro de un rango esperado.

LEGACY_PARAM_EXPECTED = {
    'qmax_G': (1e-5, 1e-2),
    'qmax_X': (1e-5, 1e-2),
    'qmax_F': (1e-6, 1e-3),
    'qmax_HMF': (1e-6, 1e-3),
    'qmax_ATC': (1e-6, 1e-3),
    'Y_Eth_G': (0.3, 0.7),
    'Y_Eth_X': (0.2, 0.6),
    'Y_Cell_G': (0.01, 0.2),
    'Y_Cell_X': (0.01, 0.25),
}

@pytest.mark.parametrize('detailed', [False, True])
def test_parameters_within_legacy_ranges(detailed):
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=detailed)
    for pname, (lo, hi) in LEGACY_PARAM_EXPECTED.items():
        assert hasattr(m, pname), f'Falta param {pname}'
        val = pe.value(getattr(m, pname))
        assert lo <= val <= hi, f'{pname} fuera de rango {lo}..{hi}: {val}'
