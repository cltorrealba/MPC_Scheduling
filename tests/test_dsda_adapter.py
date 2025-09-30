import pyomo.environ as pe

from biorefinery.optimization.dsda_adapter import (
    ROUTE_ORDER,
    extract_route_vector,
    apply_route_vector,
    one_flip_neighbors,
    evaluate_vector,
    steepest_improvement_step,
    run_local_descent,
)
from biorefinery.models.fermentation import build_fermentation_model


def _base_kwargs():
    init = {"G":5,"X":2,"F":0.5,"HMF":0.2,"ACT":0.1,"Eth":0.0,"Cell":1.0,"CO2":0.0}
    return dict(include_kinetics=True, detailed_kinetics=False, initial_concentrations=init)


def test_route_vector_round_trip():
    m = build_fermentation_model(**_base_kwargs())
    v0 = extract_route_vector(m)
    assert v0 == [1]*len(ROUTE_ORDER)
    new_v = [0 if i==0 else 1 for i,_ in enumerate(v0)]
    apply_route_vector(m, new_v)
    v1 = extract_route_vector(m)
    assert v1 == new_v


def test_one_flip_neighbors_count():
    vec = [1,0,1,0,1]
    neigh = one_flip_neighbors(vec)
    assert len(neigh) == len(vec)
    # Each neighbor differs in exactly one position
    for n in neigh:
        diff = sum(1 for a,b in zip(n,vec) if a!=b)
        assert diff == 1


def test_evaluate_vector_runs():
    res = evaluate_vector(_base_kwargs(), [1,1,1,1,1])
    assert res.objective is not None
    assert res.solved_model is not None


def test_steepest_improvement_step():
    # Start from all active; ensure function returns a result and neighbor evaluations
    best, evaluated = steepest_improvement_step(_base_kwargs(), [1,1,1,1,1])
    assert len(evaluated) == len(ROUTE_ORDER)
    assert best.vector is not None
    # Objective may or may not improve; just ensure numeric
    assert best.objective is not None


def test_run_local_descent_basic():
    res = run_local_descent(_base_kwargs(), start_vector=[1,1,1,1,1], max_iters=5, early_stop=True)
    assert 'incumbent' in res
    assert res['incumbent'].objective is not None
    # evaluated_count should be <= 1 + iters * len(routes)
    assert res['evaluated_count'] >= 1
    assert res['cache_hits'] >= 0
