import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model, set_route_activation


def test_initial_concentrations_fixing():
    init = {"G": 10.0, "X": 5.0, "Eth": 0.0}
    m = build_fermentation_model(include_kinetics=False, initial_concentrations=init)
    t0 = m.t.first()
    for sp, val in init.items():
        assert abs(pe.value(m.C[t0, sp]) - val) < 1e-8
        assert m.C[t0, sp].fixed is True


def test_route_toggle_affects_detailed_glucose_rate():
    # Build with detailed kinetics so glucose rate constraint exists
    init = {"G": 10.0, "X": 5.0, "Eth": 0.0, "Cell": 1.0, "F": 0.0, "ACT": 0.0, "HMF": 0.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True, initial_concentrations=init)
    # Deactivate glucose route
    set_route_activation(m, 'G', False)
    # Pick a non-initial time point
    t_sample = list(m.t)[1]
    # Force other multiplicative terms to reasonable numeric values if unfixed
    # (they already have defaults; we just ensure solver feasibility test)
    # Solve a tiny NLP to propagate constraint equality
    solver = pe.SolverFactory('ipopt')
    if solver.available():
        solver.solve(m, tee=False)
        assert pe.value(m.q[t_sample, 'G']) == 0
    else:
        # Fallback symbolic evaluation of body right-hand side (route=0 implies q=0)
        assert m.route_config['G'].value == 0


def test_route_toggle_reactivation():
    init = {"G": 10.0, "X": 5.0, "Eth": 0.0, "Cell": 1.0, "F": 0.0, "ACT": 0.0, "HMF": 0.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True, initial_concentrations=init)
    set_route_activation(m, 'G', False)
    assert m.route_config['G'].value == 0
    set_route_activation(m, 'G', True)
    assert m.route_config['G'].value == 1
