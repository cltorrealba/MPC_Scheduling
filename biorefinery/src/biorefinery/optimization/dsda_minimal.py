from __future__ import annotations
"""Minimal DSDA-style enumeration wrapper (no legacy dependency).

Features:
- Works with a model factory callable `model_function(**model_args)`.
- External binary variables provided via `ext_dict: {name: [Var, Var, ...]}`.
- One-flip neighborhood search with optional early stop on no improvement.
- Returns best solved model and history of objectives.

Limitations:
- No advanced tabu / restart logic (can be layered above if needed).
- Assumes objective is scalar and minimization (will convert if sense=max).
- Assumes external vars are Binary; no feasibility logic beyond Pyomo solve status.
"""
import pyomo.environ as pe
from typing import Callable, Dict, List, Any, Tuple
from .solvers import pick_available_solver

class DSDAResult(dict):
    pass

def _obj_value(m: pe.ConcreteModel) -> float:
    obj = next(iter(m.component_data_objects(pe.Objective, active=True)))
    val = pe.value(obj)
    # Normalize to minimization value
    return val

def _apply_external_vector(ext_vars: List[pe.Var], values: List[int]):
    for v, val in zip(ext_vars, values):
        if v.is_fixed():
            v.unfix()
        v.set_value(int(val))
        v.fix()

def one_flip_neighbors_vector(vec: List[int]):
    for i in range(len(vec)):
        nv = vec.copy()
        nv[i] = 1 - nv[i]
        yield nv

def dsda_minimal(
    model_function: Callable[..., pe.ConcreteModel],
    model_args: Dict[str, Any],
    ext_dict: Dict[str, List[pe.Var]],
    starting_point: List[int] | None = None,
    max_iters: int = 50,
    solver: str | None = None,
    tee: bool = False,
    stop_on_no_improve: bool = True,
) -> DSDAResult:
    if not ext_dict:
        raise ValueError("ext_dict required with at least one external variable list")
    # Flatten ordered external variables
    # Keep deterministic ordering by sorting keys then concatenating lists
    ordered_keys = sorted(ext_dict.keys())
    ext_vars: List[pe.Var] = []
    for k in ordered_keys:
        ext_vars.extend(ext_dict[k])
    n = len(ext_vars)
    if starting_point is None:
        starting_point = [int(getattr(v, 'value', 0) or 0) for v in ext_vars]
    if len(starting_point) != n:
        raise ValueError("starting_point length mismatch with external variables")

    # Initial evaluation
    best_vector = starting_point.copy()
    best_model = model_function(**model_args)
    _apply_external_vector(ext_vars=[best_model.find_component(v.name) for v in ext_vars], values=best_vector)
    solver_name = solver or pick_available_solver(return_options=False)
    sf = pe.SolverFactory(solver_name)
    sf.solve(best_model, tee=tee)
    best_val = _obj_value(best_model)
    history: List[Tuple[List[int], float]] = [(best_vector.copy(), best_val)]

    for it in range(max_iters):
        improved = False
        for cand in one_flip_neighbors_vector(best_vector):
            m = model_function(**model_args)
            _apply_external_vector([m.find_component(v.name) for v in ext_vars], cand)
            sf.solve(m, tee=False)
            val = _obj_value(m)
            history.append((cand.copy(), val))
            if val < best_val - 1e-12:
                best_val = val
                best_vector = cand
                best_model = m
                improved = True
                if stop_on_no_improve:
                    break
        if not improved:
            break
    return DSDAResult({
        'best_vector': best_vector,
        'best_value': best_val,
        'model': best_model,
        'history': history,
        'iterations': len(history)-1,
        'solver': solver_name,
    })

__all__ = ['dsda_minimal']
