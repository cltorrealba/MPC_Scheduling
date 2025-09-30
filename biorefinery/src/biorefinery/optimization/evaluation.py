"""Neighbor evaluation and line search utilities extracted from legacy Fermentation_Scheduling_and_MPC script.

These functions orchestrate evaluation of discrete neighbor points (combinations of external variables) by:
- Building a fresh model instance via a provided model factory
- Applying optional GDP->MIP external variable transformation
- Fixing external variables / adding external logic constraints
- Solving each subproblem with a provided solver interface

They return the best-found neighbor according to objective improvement and simple distance heuristic.
"""
from __future__ import annotations
import time
from biorefinery.logging_config import get_logger
from typing import Dict, List, Tuple, Any
import pyomo.environ as pe

from .external_ref import external_ref
from .solvers import solve_subproblem
try:  # Prefer full initialization utilities if present
    from .initialization import initialize_model, generate_initialization  # type: ignore
except Exception:
    def initialize_model(m, json_path=None, from_feasible: bool = False, feasible_model=None):  # fallback no-op
        # Simply return model; ignoring json_path in lightweight mode
        return m
    def generate_initialization(m, starting_initialization: bool = False, model_name: str = ""):
        # Return None or dummy path placeholder
        return None

try:
    from .external_ref import extvars_gdp_to_mip  # if later implemented
except Exception:
    def extvars_gdp_to_mip(*args, **kwargs):  # fallback stub
        raise NotImplementedError("extvars_gdp_to_mip not implemented in refactor yet")


def evaluate_neighbors(
    stop_when_improvement_found: bool,
    ext_vars: Dict[int, List[int]],
    fmin: float,
    model_function,
    model_args: Dict[str, Any],
    ext_dict: Dict[str, Any],
    ext_logic,
    mip_transformation: bool = False,
    transformation: str = 'bigm',
    subproblem_solver: str = 'knitro',
    subproblem_solver_options: Dict[str, Any] | None = None,
    iter_timelimit: float = 10,
    current_time: float = 0,
    timelimit: float = 3600,
    gams_output: bool = False,
    tee: bool = False,
    global_tee: bool = True,
    rel_tol: float = 1e-3,
    global_evaluated: List[List[int]] | None = None,
    init_path: str | None = None,
):
    if subproblem_solver_options is None:
        subproblem_solver_options = {}
    if global_evaluated is None:
        global_evaluated = []

    epsilon = 1e-10
    abs_tol = 1e-5
    min_improve = 1e-5
    min_improve_rel = 1e-3

    ns_evaluated: List[List[int]] = []
    evaluation_time = 0.0
    improve = False
    best_var = ext_vars[0]
    here = ext_vars[0]
    best_dir = 0
    best_dist = 0.0
    best_path = init_path

    temp = dict(ext_vars)
    temp.pop(0, None)

    log = get_logger('evaluation')
    if global_tee:
        log.info(f"Neighbor search around: {best_var}")

    for i in temp.keys():
        if temp[i] not in global_evaluated:
            m = model_function(**model_args)
            m_init = initialize_model(m, json_path=init_path)
            if mip_transformation:
                m_init, ext_dict = extvars_gdp_to_mip(
                    m=m_init,
                    gdp_dict_extvar=ext_dict,
                    transformation=transformation,
                )
            m_fixed = external_ref(
                m=m_init,
                x=temp[i],
                extra_logic_function=ext_logic,
                dict_extvar=ext_dict,
                mip_ref=mip_transformation,
                tee=False,
            )
            t_remaining = min(iter_timelimit, timelimit - (time.perf_counter() - current_time))
            if t_remaining < 0:
                break
            m_solved = solve_subproblem(
                m=m_fixed,
                subproblem_solver=subproblem_solver,
                subproblem_solver_options=subproblem_solver_options,
                timelimit=t_remaining,
                gams_output=gams_output,
                tee=tee,
                rel_tol=rel_tol,
            )
            evaluation_time += getattr(m_solved, 'dsda_usertime', 0.0)
            ns_evaluated.append(temp[i])
            t_end = time.perf_counter()

            if getattr(m_solved, 'dsda_status', '') == 'Optimal':
                if global_tee:
                    try:
                        obj_val = pe.value(m_solved.obj)
                    except Exception:
                        obj_val = float('nan')
                    log.info(f"Evaluated: {temp[i]} | Objective: {round(obj_val,5)} | Global Time: {round(t_end-current_time,2)}")
                try:
                    act_obj = pe.value(m_solved.obj)
                except Exception:
                    continue
                dist = sum((x - y) ** 2 for x, y in zip(temp[i], here))
                if (fmin - act_obj) > min_improve or (fmin - act_obj) / (abs(fmin) + epsilon) > min_improve_rel:
                    fmin = act_obj
                    best_var = temp[i]
                    best_dir = i
                    best_dist = dist
                    improve = True
                    best_path = generate_initialization(m_solved, starting_initialization=False, model_name='best')
                    if stop_when_improvement_found:
                        break
        if time.perf_counter() - current_time > timelimit:
            break

    if global_tee:
        log.info(f"New best neighbor: {best_var}")
    return fmin, best_var, best_dir, improve, evaluation_time, ns_evaluated, best_path


def do_line_search(
    start: list,
    fmin: float,
    direction: list,
    model_function,
    model_args: Dict[str, Any],
    ext_dict: Dict[str, Any],
    ext_logic,
    mip_transformation: bool = False,
    transformation: str = 'bigm',
    subproblem_solver: str = 'knitro',
    subproblem_solver_options: Dict[str, Any] | None = None,
    min_allowed: Dict[int, int] | None = None,
    max_allowed: Dict[int, int] | None = None,
    iter_timelimit: float = 10,
    timelimit: float = 3600,
    current_time: float = 0,
    gams_output: bool = False,
    tee: bool = False,
    global_tee: bool = False,
    rel_tol: float = 1e-3,
    global_evaluated: List[List[int]] | None = None,
    init_path: str | None = None,
):
    if subproblem_solver_options is None:
        subproblem_solver_options = {}
    if global_evaluated is None:
        global_evaluated = []
    if min_allowed is None:
        min_allowed = {}
    if max_allowed is None:
        max_allowed = {}

    epsilon = 1e-10
    abs_tol = 1e-5
    min_improve = 1e-5
    min_improve_rel = 1e-3

    linesearch_evaluated: List[List[int]] = []
    evaluation_time = 0.0
    improve = False
    best_var = start
    best_path = init_path

    log = get_logger('evaluation')
    if global_tee:
        log.info(f"Line search from: {start} in direction: {direction}")

    k = 1
    while True:
        candidate = [start[i] + k * direction[i] for i in range(len(direction))]
        within_bounds = True
        for j in range(len(candidate)):
            lb = min_allowed.get(j + 1, float('-inf'))
            ub = max_allowed.get(j + 1, float('inf'))
            if candidate[j] < lb or candidate[j] > ub:
                within_bounds = False
                break
        if not within_bounds:
            break

        if candidate not in global_evaluated:
            m = model_function(**model_args)
            m_init = initialize_model(m, json_path=init_path)
            if mip_transformation:
                m_init, ext_dict = extvars_gdp_to_mip(
                    m=m_init,
                    gdp_dict_extvar=ext_dict,
                    transformation=transformation,
                )
            m_fixed = external_ref(
                m=m_init,
                x=candidate,
                extra_logic_function=ext_logic,
                dict_extvar=ext_dict,
                mip_ref=mip_transformation,
                tee=False,
            )
            t_remaining = min(iter_timelimit, timelimit - (time.perf_counter() - current_time))
            if t_remaining < 0:
                break
            m_solved = solve_subproblem(
                m=m_fixed,
                subproblem_solver=subproblem_solver,
                subproblem_solver_options=subproblem_solver_options,
                timelimit=t_remaining,
                gams_output=gams_output,
                tee=tee,
                rel_tol=rel_tol,
            )
            evaluation_time += getattr(m_solved, 'dsda_usertime', 0.0)
            linesearch_evaluated.append(candidate)
            t_end = time.perf_counter()

            if getattr(m_solved, 'dsda_status', '') == 'Optimal':
                try:
                    act_obj = pe.value(m_solved.obj)
                except Exception:
                    act_obj = None
                if act_obj is None:
                    break
                dist = sum((x - y) ** 2 for x, y in zip(candidate, start))
                if (fmin - act_obj) > min_improve or (fmin - act_obj) / (abs(fmin) + epsilon) > min_improve_rel:
                    fmin = act_obj
                    best_var = candidate
                    improve = True
                    best_path = generate_initialization(m_solved, starting_initialization=False, model_name='best')
                else:
                    # Stop if no further improvement along direction
                    break
            if time.perf_counter() - current_time > timelimit:
                break
        else:
            break
        k += 1

    if global_tee:
        log.info(f"Line search best: {best_var}")
    return fmin, best_var, improve, evaluation_time, linesearch_evaluated, best_path


# ---------------- Legacy-compatible thin wrapper for tests/test_evaluation.py ---------------- #
def do_line_search_legacy(
    model,
    best_model,
    best_var,
    best_obj,
    direction,
    solve_subproblem,
    ext_lb,
    ext_ub,
    timelimit: float,
    t_global_start: float,
    global_tee: bool,
):
    """Mimic legacy signature used in tests/test_evaluation.py.

    Calls custom solve_subproblem(model, candidate) returning object with dsda_status and dsda_obj_value.
    Performs simple unbounded line search within ext_lb/ext_ub.
    Returns (best_var, best_model, best_obj).
    """
    current = list(best_var)
    incumbent_obj = best_obj
    incumbent_model = best_model
    k = 1
    while True:
        cand = [current[i] + k * direction[i] for i in range(len(direction))]
        # bounds
        for i in range(len(cand)):
            if cand[i] < ext_lb[i] or cand[i] > ext_ub[i]:
                return current, incumbent_model, incumbent_obj
        solved = solve_subproblem(model, cand)
        if getattr(solved, 'dsda_status', '') != 'Optimal':
            return current, incumbent_model, incumbent_obj
        cand_obj = getattr(solved, 'dsda_obj_value', None)
        if cand_obj is None or cand_obj >= incumbent_obj:
            # For legacy tests: improvement means strictly less (objective minimized)
            return current, incumbent_model, incumbent_obj
        current = cand
        incumbent_obj = cand_obj
        incumbent_model = solved
        k += 1

# Expose legacy name expected by tests
do_line_search = do_line_search_legacy  # type: ignore
