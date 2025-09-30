import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model, set_route_activation


def _build_full():
    init = {"G":10,"X":5,"F":1.0,"HMF":0.5,"ACT":0.2,"Eth":0.0,"Cell":1.0}
    return build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
                                    initial_concentrations=init)


def test_new_detailed_kinetics_components_present():
    m = _build_full()
    # Constraint names should exist
    assert hasattr(m, 'q_furfural_rate')
    assert hasattr(m, 'q_hmf_rate')
    assert hasattr(m, 'q_acetate_rate')
    # Balance constraints for new species
    assert hasattr(m.concentration_balances, 'bal_F')
    assert hasattr(m.concentration_balances, 'bal_HMF')
    assert hasattr(m.concentration_balances, 'bal_ACT')


def test_toggle_disables_furfural_rate_symbolically():
    m = _build_full()
    set_route_activation(m,'F', False)
    # Pick second time point
    t_sample = list(m.t)[1]
    # Optional solve if ipopt is available
    solver = pe.SolverFactory('ipopt')
    if solver.available():
        solver.solve(m, tee=False)
        assert pe.value(m.q[t_sample,'F']) == 0
    else:
        # Evaluate RHS logic: route_config['F']==0 implies q[F]==0 after solve; pre-solve we at least check param
        assert m.route_config['F'].value == 0


def test_acetate_balance_couples_hmf_and_act():
    m = _build_full()
    # Deactivate ACT uptake to isolate production term
    set_route_activation(m,'ACT', False)
    t_sample = list(m.t)[1]
    solver = pe.SolverFactory('ipopt')
    if solver.available():
        solver.solve(m, tee=False)
        # If uptake disabled q[ACT]==0 then dCdt_ACT * final_time should equal q[HMF]*Y_ACT_HMF
        lhs = pe.value(m.dCdt[t_sample,'ACT'] * m.final_time)
        rhs = pe.value(m.q[t_sample,'HMF'] * m.Y_ACT_HMF)
        assert abs(lhs - rhs) < 1e-6
    else:
        assert m.route_config['ACT'].value == 0
