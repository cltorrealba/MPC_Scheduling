import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

def test_build_fermentation_model_basic():
    m = build_fermentation_model(n_f_elements_t=1, total_f_elements_t=50)
    assert isinstance(m, pe.ConcreteModel)
    assert hasattr(m, 't') and len(list(m.t)) > 0
    assert hasattr(m, 'j') and 'Eth' in list(m.j)
    assert hasattr(m, 'obj')
    # Check derivative linkage existence
    assert hasattr(m, 'dCdt') and hasattr(m, 'dMdt')


def test_build_fermentation_model_with_kinetics_flag():
    m = build_fermentation_model(include_kinetics=True)
    # Kinetics params should exist
    for p in [
        'Y_CO2_G','Y_CO2_X','qmax_G','qmax_X','Y_Eth_G','Y_Eth_X','KIP_G','KSP_G','KIP_X','KSP_X'
    ]:
        assert hasattr(m, p), f"Missing kinetics Param {p}"
    # Kinetics variables sets
    assert hasattr(m, 'q') and hasattr(m, 'R')
    assert len(m.kinetic_species) > 0
    assert len(m.product_reactions) > 0
    # Stub constraint presence
    assert hasattr(m, 'ethanol_rate') and hasattr(m, 'co2_rate')


def test_build_fermentation_model_without_kinetics_flag():
    m = build_fermentation_model(include_kinetics=False)
    assert not hasattr(m, 'q')
    assert not hasattr(m, 'R')
    # Representative kinetics parameter should be absent
    assert not hasattr(m, 'qmax_G')


def test_build_fermentation_model_detailed_kinetics_requires_base():
    # detailed_kinetics without include_kinetics should raise
    try:
        build_fermentation_model(detailed_kinetics=True)
        assert False, "Expected ValueError when detailed_kinetics=True without include_kinetics"
    except ValueError:
        pass


def test_build_fermentation_model_with_detailed_kinetics():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True)
    # Detailed constraints should be present
    assert hasattr(m, 'q_glucose_rate')
    assert hasattr(m, 'q_xylose_rate')
    # Verify at least one non-first time point has a constraint body referencing inhibition terms
    t_points = list(m.t)
    if len(t_points) > 1:
        t_sample = t_points[1]
        # Access body to ensure Pyomo expression constructed (will raise if malformed)
        _ = m.q_glucose_rate[t_sample].body
        _ = m.q_xylose_rate[t_sample].body
