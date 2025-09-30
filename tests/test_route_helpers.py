import pyomo.environ as pe
from biorefinery.models.fermentation import (
    build_fermentation_model,
    set_route_activation,
    set_routes_activation,
    optimize_routes_local_descent,
)


def evaluator_from_model(m):
    def _eval(vec):
        # Apply vector to model
        for k, v in vec.items():
            route = k
            set_route_activation(m, route, bool(v))
        # Pseudo objective: negative sum of active routes (to encourage flips)
        obj = -sum(vec.values())
        return obj, True
    return _eval


def test_bulk_toggle_and_fixing():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False)
    # deactivate two routes
    set_routes_activation(m, {'G':0, 'X':0})
    for t in m.t:
        assert m.q[t,'G'].fixed and abs(m.q[t,'G'].value) < 1e-12
        assert m.q[t,'X'].fixed and abs(m.q[t,'X'].value) < 1e-12
    # reactivate one
    set_route_activation(m, 'G', True)
    for t in m.t:
        assert not m.q[t,'G'].fixed
        assert m.q[t,'X'].fixed


def test_local_descent_wrapper():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False)
    eval_fn = evaluator_from_model(m)
    result = optimize_routes_local_descent(m, eval_fn, max_iters=3)
    assert 'best_vector' in result and 'best_value' in result
    assert isinstance(result['history'], list)
