import importlib
import pytest
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model

LEGACY_MODULE = 'biorefinery_models.Fermentation_Scheduling_and_MPC'
LEGACY_BUILDER = 'build_fermentation_one_time_step_optimizing_flows_pH_open_loop_pessimization'


def _load_legacy():
    try:
        mod = importlib.import_module(LEGACY_MODULE)
        if hasattr(mod, LEGACY_BUILDER):
            return getattr(mod, LEGACY_BUILDER)
    except Exception:
        return None
    return None


legacy_builder = _load_legacy()


@pytest.mark.skipif(legacy_builder is None, reason='Legacy no disponible')
@pytest.mark.xfail(reason='Baseline dinámica aún no establecida; se implementará en futura iteración Fase 4', strict=False)
def test_dynamic_series_alignment_placeholder():
    # Construye modelos (legacy y nuevo) y compara tamaño de discretización y presencia de especies
    m_legacy = legacy_builder(n_f_elements_t=2, total_f_elements_t=2)  # horizonte corto
    m_new = build_fermentation_model(include_kinetics=True, detailed_kinetics=True, n_f_elements_t=2, total_f_elements_t=2)

    # Verificar conjunto de especies clave
    key_species = {'G','X','Eth','Cell'}
    for sp in key_species:
        assert sp in m_new.j

    # Comparar número de puntos de tiempo (ambos definen ContinuousSet [0,1]; no resolución aún)
    # Placeholder: simplemente asegurar que existen derivadas para new
    assert hasattr(m_new, 'dCdt')
    assert hasattr(m_new, 'dMdt')

    # Futuro: resolver ambos modelos (si restricciones dinámicas completas) y comparar trayectorias con tolerancias.
    # Marca xfail hasta que se defina baseline numérica conjunta.
    pytest.xfail('Pendiente implementación baseline dinámica cuantitativa')
