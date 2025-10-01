from types import SimpleNamespace
from biorefinery.scripts.run_integrated_iterative import run


def test_run_integrated_iterative_two_iters():
    args = SimpleNamespace(iterations=2, initial_demand=10.0, theoretical_max_ethanol=100.0,
                           weight_yield=0.5, weight_demand=0.5, no_solve_fermentation=True, print=False)
    res = run(args)
    # At least one iteration should run
    assert len(res) >= 1
    for it in res:
        assert 0.0 <= it.aggregate_score <= 1.0
    # Score should be non-decreasing or stable (heuristic batch each iteration until demand covered)
    scores = [r.aggregate_score for r in res]
    assert all(b >= a - 1e-9 for a, b in zip(scores, scores[1:]))