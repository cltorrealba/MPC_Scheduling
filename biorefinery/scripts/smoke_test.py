"""Quick smoke test for refactored optimization utilities.

Creates a trivial Pyomo model with a couple of binary 'external' variables
wrapped as if they were GDP external variables, then runs dsda_enumeration
with a tiny neighborhood to verify that the refactored modules import and
basic solving loop executes without crashing.
"""
from __future__ import annotations
import pyomo.environ as pe
import time

from biorefinery.optimization.dsda_minimal import dsda_minimal

# Minimal model factory -------------------------------------------------------

def tiny_model():
    m = pe.ConcreteModel()
    # Two 'external' binary decisions we will treat as external vars
    m.x1 = pe.Var(domain=pe.Binary)
    m.x2 = pe.Var(domain=pe.Binary)
    # A simple continuous var with convex objective component
    m.y = pe.Var(bounds=(0, 10))
    # Simple linking constraint to make objective depend on binaries
    m.c1 = pe.Constraint(expr=m.y >= 2*m.x1 + m.x2)
    # Objective prefers y small and some pattern in binaries
    m.obj = pe.Objective(expr= (m.y - 1)**2 + 0.5*m.x1 + 0.25*m.x2 )
    return m

# External variable dictionary mimic: map a synthetic key to an ordered set.
# For the minimal case we just pass an empty dict to dsda_enumeration and
# allow get_external_information to rebuild it from the model if needed.

def main():
    start_time = time.perf_counter()
    model_args = {}
    start_point = [0, 0]  # x1, x2
    # We fake an ext_dict: in the legacy code ext_dict is provided, but the utility
    # get_external_information(m, ext_dict) will reconstruct details we need if ext_dict
    # already maps keys to pyomo BoolVars or Disjuncts. Here we handle manually below.

    # Build one instance to grab components and craft an ext_dict
    m0 = tiny_model()
    # emulate external variable list using the underlying Var objects
    ext_dict = { 'ext_bin': [m0.x1, m0.x2] }

    # Run enumeration with a very small time limit
    res = dsda_minimal(
        model_function=tiny_model,
        model_args=model_args,
        ext_dict=ext_dict,
        starting_point=start_point,
        max_iters=10,
        tee=False,
    )
    solved = res['model']
    print("Best vector:", res['best_vector'])
    print("Best value:", res['best_value'])
    print("History length:", len(res['history']))
    print("Iterations:", res['iterations'])
    print("Final objective (check):", pe.value(solved.obj))
    print("Elapsed wall time:", round(time.perf_counter() - start_time, 2), 's')

if __name__ == "__main__":
    main()
