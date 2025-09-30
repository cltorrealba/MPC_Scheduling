"""Lightweight DSDA adapter for route toggling in the fermentation model.

This module offers a minimal, Pyomo-internal (no GAMS) discrete search helper
focused on the binary route activation parameters exposed by
`biorefinery.models.fermentation.build_fermentation_model` via `route_config`.

Goals:
- Represent current route activation as a binary vector (list[int]).
- Apply a binary vector to an existing model without rebuilding.
- Generate 1-flip neighborhood vectors.
- Evaluate a vector by fixing route_config params and (re)solving.
- Perform a single steepest-improving move (no full DSDA line search loops).

This is intentionally simpler than the full dsda.py enumerator so tests can
validate correctness quickly and provide a scaffold for future integration.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Sequence, Tuple, Dict, Iterable, Callable, Optional, Set
import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model, set_route_activation

RouteVector = List[int]

# Ordered route names consistent with fermentation model route_config creation
ROUTE_ORDER = ["G","X","F","HMF","ACT"]

@dataclass
class EvalResult:
    vector: RouteVector
    objective: float
    solved_model: pe.ConcreteModel
    solver_status: str


def extract_route_vector(model: pe.ConcreteModel) -> RouteVector:
    if not hasattr(model, 'route_config'):
        raise AttributeError("Model missing route_config (build with include_kinetics=True)")
    return [int(model.route_config[r].value) for r in ROUTE_ORDER]


def apply_route_vector(model: pe.ConcreteModel, vector: Sequence[int]):
    if len(vector) != len(ROUTE_ORDER):
        raise ValueError("Vector length mismatch with ROUTE_ORDER")
    for r, v in zip(ROUTE_ORDER, vector):
        set_route_activation(model, r, bool(v))


def one_flip_neighbors(vector: Sequence[int]) -> List[RouteVector]:
    neigh = []
    for i in range(len(vector)):
        new_v = list(vector)
        new_v[i] = 1 - new_v[i]
        neigh.append(new_v)
    return neigh


def solve_with_routes(model: pe.ConcreteModel, solver: str = 'ipopt', tee: bool = False) -> Tuple[float,str]:
    s = pe.SolverFactory(solver)
    if not s.available():
        return float('inf'), 'solver_unavailable'
    res = s.solve(model, tee=tee)
    # If infeasible or no obj value, return inf
    try:
        val = pe.value(model.obj)
    except Exception:
        return float('inf'), str(res.solver.status)
    return float(val), f"{res.solver.status}/{res.solver.termination_condition}"  # type: ignore


def evaluate_vector(model_builder_kwargs: Dict, vector: Sequence[int], solver: str='ipopt') -> EvalResult:
    # Build a fresh model to avoid cumulative numerical artifacts
    m = build_fermentation_model(**model_builder_kwargs)
    apply_route_vector(m, vector)
    obj, status = solve_with_routes(m, solver=solver, tee=False)
    return EvalResult(vector=list(vector), objective=obj, solved_model=m, solver_status=status)


def steepest_improvement_step(model_builder_kwargs: Dict, current_vector: RouteVector, solver: str='ipopt') -> Tuple[EvalResult, List[EvalResult]]:
    """Evaluate 1-flip neighbors and return best improving result (or current if none).

    Returns (best_result, all_neighbor_results).
    """
    base_res = evaluate_vector(model_builder_kwargs, current_vector, solver=solver)
    neighbors = one_flip_neighbors(current_vector)
    evaluated: List[EvalResult] = []
    best = base_res
    for v in neighbors:
        res = evaluate_vector(model_builder_kwargs, v, solver=solver)
        evaluated.append(res)
        if res.objective < best.objective:  # objective is minimized
            best = res
    return best, evaluated


def run_local_descent(
    model_builder_kwargs: Dict,
    start_vector: RouteVector | None = None,
    solver: str = 'ipopt',
    max_iters: int = 20,
    early_stop: bool = True,
    record_history: bool = True,
) -> Dict[str, any]:
    """Iteratively apply steepest 1-flip improvement until no progress or limits.

    Returns dict with keys:
      history: list[EvalResult] (if record_history)
      incumbent: EvalResult (final solution)
      iterations: int performed
      cache_hits: int (neighbor evaluations skipped due to caching)
      evaluated_count: int (number of distinct vectors solved)
    """
    if start_vector is None:
        start_vector = [1] * len(ROUTE_ORDER)
    history: List[EvalResult] = []
    cache: Dict[Tuple[int,...], EvalResult] = {}
    cache_hits = 0

    # Seed
    incumbent = evaluate_vector(model_builder_kwargs, start_vector, solver=solver)
    cache[tuple(start_vector)] = incumbent
    if record_history:
        history.append(incumbent)

    for it in range(max_iters):
        best_neighbor = incumbent
        improved = False
        for cand in one_flip_neighbors(incumbent.vector):
            key = tuple(cand)
            if key in cache:
                cache_hits += 1
                cand_res = cache[key]
            else:
                cand_res = evaluate_vector(model_builder_kwargs, cand, solver=solver)
                cache[key] = cand_res
            if cand_res.objective < best_neighbor.objective:
                best_neighbor = cand_res
                improved = True
        if improved:
            incumbent = best_neighbor
            if record_history:
                history.append(incumbent)
        else:
            if early_stop:
                break
    result = {
        'incumbent': incumbent,
        'iterations': len(history)-1 if record_history else None,
        'cache_hits': cache_hits,
        'evaluated_count': len(cache),
    }
    if record_history:
        result['history'] = history
    return result

__all__ = [
    'ROUTE_ORDER',
    'extract_route_vector',
    'apply_route_vector',
    'one_flip_neighbors',
    'evaluate_vector',
    'steepest_improvement_step',
    'run_local_descent',
    'EvalResult'
]
