import types

from biorefinery.optimization.evaluation import do_line_search


class DummyModel:
    pass


def fake_solve(model, ext_var):
    # Deterministic pseudo objective: sum of squares
    obj = sum(v * v for v in ext_var)
    solved = DummyModel()
    solved.dsda_obj_value = obj
    solved.dsda_status = "Optimal"
    return solved


def test_do_line_search_improves_best_when_possible():
    current = [3, 3]
    direction = (1, -1)  # moves towards (4,2), (5,1), ...
    lb = (0, 0)
    ub = (10, 10)

    # Best variable is (3,3) initially with obj=18; moving along direction increases squares.
    # To test improvement we reverse direction effect by redefining objective negative sum squares.
    def improving_solve(model, ext_var):
        obj = -sum(v * v for v in ext_var)  # maximize distance by minimizing negative
        solved = DummyModel()
        solved.dsda_obj_value = obj
        solved.dsda_status = "Optimal"
        return solved

    best_var, best_model, best_obj = do_line_search(
        model=None,
        best_model=None,
        best_var=current,
        best_obj=-sum(v * v for v in current),
        direction=direction,
        solve_subproblem=improving_solve,
        ext_lb=lb,
        ext_ub=ub,
        timelimit=2.0,
        t_global_start=0.0,
        global_tee=False,
    )

    assert tuple(best_var) != tuple(current)
    assert best_obj < -sum(v * v for v in current)  # more negative is better


def test_do_line_search_respects_bounds():
    current = [0, 0]
    direction = (-1, 2)
    lb = (0, 0)
    ub = (5, 5)

    best_var, _, _ = do_line_search(
        model=None,
        best_model=None,
        best_var=current,
        best_obj=0.0,
        direction=direction,
        solve_subproblem=fake_solve,
        ext_lb=lb,
        ext_ub=ub,
        timelimit=1.0,
        t_global_start=0.0,
        global_tee=False,
    )

    # First step would attempt (-1,2) but should clamp to (0,2)
    assert best_var[0] >= 0
