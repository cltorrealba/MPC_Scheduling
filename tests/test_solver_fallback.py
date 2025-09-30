import types
import pyomo.environ as pe
from biorefinery.optimization.solvers import solve_subproblem


class DummyResults:
    class Solver:
        termination_condition = 'optimal'
        user_time = 0.01
    solver = Solver()


def tiny_model():
    m = pe.ConcreteModel()
    m.x = pe.Var(initialize=1.0)
    m.obj = pe.Objective(expr=m.x**2)
    return m


def test_fallback_to_solver_not_available(monkeypatch):
    # Monkeypatch SolverFactory to always return None to simulate missing solvers
    import pyomo.opt.base.solvers as base

    real_factory = base.SolverFactory

    def fake_factory(*args, **kwargs):  # always unavailable
        return None

    monkeypatch.setattr(base, 'SolverFactory', fake_factory)

    m = tiny_model()
    solved = solve_subproblem(m, subproblem_solver='nonexistent', allow_fallback=False)
    assert solved.dsda_status == 'Solver_Not_Available'

    # restore not strictly necessary (monkeypatch handles it)


def test_success_path_with_direct_solve(monkeypatch):
    # Monkeypatch GAMS attempt to fail, direct solver to succeed (pretend ipopt exists)
    import pyomo.opt.base.solvers as base

    real_factory = base.SolverFactory

    class FakeSolver:
        def available(self, arg):
            return True
        def solve(self, model, tee=False):
            model.results = DummyResults()
            return model.results

    calls = []

    def conditional_factory(name, solver=None):
        calls.append((name, solver))
        if name == 'gams':
            return None  # force skip
        return FakeSolver()

    monkeypatch.setattr(base, 'SolverFactory', conditional_factory)

    m = tiny_model()
    solved = solve_subproblem(m, subproblem_solver='ipopt', allow_fallback=False)
    assert solved.dsda_status == 'Optimal'
    assert any(c[0] == 'gams' for c in calls)
