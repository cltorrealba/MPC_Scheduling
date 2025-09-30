import pyomo.environ as pe

from biorefinery.models.fermentation import (
    build_fermentation_model,
    set_route_activation,
    get_route_external_variables,
)


def test_route_monotonicity_ethanol():
    """Disabling any single route should not increase final ethanol (objective worsens or stays)."""
    init = {"G":10,"X":5,"F":1.0,"HMF":0.5,"ACT":0.2,"Eth":0.0,"Cell":1.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
                                 initial_concentrations=init)
    solver = pe.SolverFactory('ipopt')
    if not solver.available():
        # Skip meaningful numeric regression if solver missing
        return
    solver.solve(m, tee=False)
    base_eth = pe.value(m.C[m.t.last(), 'Eth'])

    routes = ['G','X','F','HMF','ACT']
    for r in routes:
        set_route_activation(m, r, False)
        solver.solve(m, tee=False)
        eth_val = pe.value(m.C[m.t.last(), 'Eth'])
        # Ethanol should not increase (base maximiza Eth) when removing a route
        assert eth_val <= base_eth + 1e-8, f"Route {r} deactivation unexpectedly increased ethanol"
        set_route_activation(m, r, True)

    # External vars snapshot consistency
    ext = get_route_external_variables(m)
    assert all(k.startswith('route_active_') for k in ext.keys())
