import pyomo.environ as pe
import pytest
from biorefinery.optimization.dsda_minimal import dsda_minimal

def model_factory():
    m = pe.ConcreteModel()
    m.x1 = pe.Var(domain=pe.Binary)
    m.x2 = pe.Var(domain=pe.Binary)
    m.y = pe.Var(bounds=(0, 10))
    m.c1 = pe.Constraint(expr=m.y >= 2*m.x1 + m.x2)
    # Minimize (y-1)^2 + cost on binaries
    m.obj = pe.Objective(expr=(m.y - 1)**2 + 0.5*m.x1 + 0.25*m.x2)
    return m

@pytest.mark.timeout(60)
def test_dsda_minimal_improves():
    # Start from vector forcing y high (x1=1,x2=1)
    start = [1,1]
    ext_dict = {'bins':[model_factory().x1, model_factory().x2]}
    res = dsda_minimal(model_function=model_factory, model_args={}, ext_dict=ext_dict, starting_point=start, max_iters=5)
    assert len(res['history']) >= 1
    # Best vector should not be worse than start
    start_model = model_factory()
    start_model.x1.set_value(1); start_model.x1.fix()
    start_model.x2.set_value(1); start_model.x2.fix()
    pe.SolverFactory(res['solver']).solve(start_model)
    start_val = pe.value(start_model.obj)
    assert res['best_value'] <= start_val + 1e-9
