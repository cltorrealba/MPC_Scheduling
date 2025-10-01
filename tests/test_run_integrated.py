from types import SimpleNamespace
from biorefinery.scripts.run_integrated import run


def test_run_integrated_basic():
    args = SimpleNamespace(no_solve_fermentation=True, weight_yield=0.5, weight_demand=0.5, print=False)
    res = run(args)
    # Score should be between 0 and 1
    assert 0.0 <= res.score <= 1.0
    # Demand fraction should be >= 0 since we scheduled production
    assert res.demand_fraction >= 0.0
    # With no solve fermentation, yield component may be very small (Cin effect); still non-negative
    assert res.yield_fraction >= 0.0
