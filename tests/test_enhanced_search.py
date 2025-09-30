from biorefinery.models.fermentation import (
    build_fermentation_model,
    optimize_routes_local_descent,
    optimize_routes_multi_start,
    set_route_activation,
)


def pseudo_eval_factory(model):
    # Objective: penalize active routes except keep at least one (feasible always True)
    def _eval(vec):
        # apply
        for r, v in vec.items():
            model.route_config[r] = v
        active = sum(vec.values())
        if active == 0:
            # large penalty if all off
            return 1e3, True
        # prefer fewer actives but reward keeping glucose if present
        obj = active - 0.1 * vec.get('G', 0)
        return obj, True
    return _eval


def test_local_descent_caching_and_tabu():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False)
    evaluator = pseudo_eval_factory(m)
    res = optimize_routes_local_descent(m, evaluator, max_iters=5, cache=True, tabu_length=2)
    assert 'cache_hits' in res and 'evaluated_count' in res
    # With 5 routes there should be at least some evaluations
    assert res['evaluated_count'] >= 1
    assert res['cache_hits'] >= 0


def test_multi_start():
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False)
    evaluator = pseudo_eval_factory(m)
    result = optimize_routes_multi_start(m, evaluator, starts=3, max_iters=3, seed=42)
    assert 'best_overall' in result and 'runs' in result
    assert len(result['runs']) == 3
    # Each run should have a start vector
    assert all('start_vector' in r for r in result['runs'])
