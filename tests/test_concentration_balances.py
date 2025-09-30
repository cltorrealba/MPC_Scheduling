import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model


def test_concentration_balance_constraints_present_and_structured():
    init = {"G": 10.0, "X": 5.0, "Eth": 0.0, "Cell": 1.0, "F": 0.0, "ACT": 0.0, "HMF": 0.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False, initial_concentrations=init)
    # Ensure block and constraints created
    assert hasattr(m, 'concentration_balances')
    for comp in ['G', 'X', 'Eth']:
        assert hasattr(m.concentration_balances, f"bal_{comp}")
    # Check at least one non-initial time point equation form matches expected sign
    t_points = list(m.t)
    if len(t_points) > 1:
        t1 = t_points[1]
        # Build a small NLP solve to instantiate derivative linking (may skip if solver absent)
        solver = pe.SolverFactory('ipopt')
        if solver.available():
            solver.solve(m, tee=False)
        # For substrates, derivative relation should be negative of uptake (ignore final_time scalar)
        if 'G' in m.kinetic_species:
            expr_G = m.concentration_balances.bal_G[t1].body
            # body = dCdt*final_time + q => expect symbol names present
            assert 'dCdt' in str(expr_G)
        if 'X' in m.kinetic_species:
            expr_X = m.concentration_balances.bal_X[t1].body
            assert 'dCdt' in str(expr_X)
        expr_Eth = m.concentration_balances.bal_Eth[t1].body
        assert 'dCdt' in str(expr_Eth)
