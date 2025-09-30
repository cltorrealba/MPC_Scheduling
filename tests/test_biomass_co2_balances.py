import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model, set_route_activation


def _model():
    init = {"G":10,"X":5,"F":1.0,"HMF":0.5,"ACT":0.2,"Eth":0.0,"Cell":1.0,"CO2":0.0}
    return build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
                                    initial_concentrations=init)


def test_biomass_and_co2_constraints_present():
    m = _model()
    assert hasattr(m.concentration_balances, 'bal_Cell')
    assert hasattr(m.concentration_balances, 'bal_CO2')


def test_growth_reduces_when_glucose_route_off():
    m = _model()
    solver = pe.SolverFactory('ipopt')
    if not solver.available():
        return
    solver.solve(m, tee=False)
    base_cell = pe.value(m.C[m.t.last(), 'Cell'])
    # Turn off glucose and xylose to remove growth drivers
    set_route_activation(m,'G', False)
    set_route_activation(m,'X', False)
    solver.solve(m, tee=False)
    new_cell = pe.value(m.C[m.t.last(), 'Cell'])
    # Without G/X uptake, growth term should vanish; maintenance may reduce cell
    assert new_cell <= base_cell + 1e-8


def test_co2_increases_with_active_substrates():
    m = _model()
    solver = pe.SolverFactory('ipopt')
    if not solver.available():
        return
    solver.solve(m, tee=False)
    base_co2 = pe.value(m.C[m.t.last(), 'CO2'])
    # Disable all CO2-producing routes
    for r in ['G','X','HMF']:
        set_route_activation(m, r, False)
    solver.solve(m, tee=False)
    new_co2 = pe.value(m.C[m.t.last(), 'CO2'])
    assert new_co2 <= base_co2 + 1e-8
