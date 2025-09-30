"""DSDA (Discrete Steepest Descent Algorithm) orchestration.

This module moves the enumeration logic out of the legacy script.
"""
from __future__ import annotations
import time
from biorefinery.logging_config import get_logger
import numpy as np
import pyomo.environ as pe

from .evaluation import evaluate_neighbors, do_line_search
from .external_ref import external_ref, get_external_information, extvars_gdp_to_mip
from .initialization import initialize_model, generate_initialization
from .neighborhoods import (
    neighborhood_k_eq_2,
    neighborhood_k_eq_inf,
    neighborhood_k_eq_l_natural,
    neighborhood_k_eq_l_natural_modified,
    neighborhood_k_eq_m_natural,
    neighborhood_k_eq_all,
    find_actual_neighbors,
)
from .solvers import solve_subproblem


def dsda_enumeration(
    k,
    model_function,
    model_args: dict,
    starting_point: list,
    ext_dict: dict,
    ext_logic,
    mip_transformation: bool = False,
    transformation: str = 'bigm',
    provide_starting_initialization: bool = False,
    feasible_model=None,
    subproblem_solver: str = 'conopt4',
    subproblem_solver_options: dict | None = None,
    iter_timelimit: float = 1000,
    timelimit: float = 3600,
    gams_output: bool = False,
    tee: bool = False,
    global_tee: bool = True,
    rel_tol: float = 1e-3,
    scaling: bool = False,
    scale_factor: float = 1.0,
    stop_neigh_verif_when_improv: bool = False,
    route_initial: list | None = None,
    obj_route_initial: list | None = None,
):
    if subproblem_solver_options is None:
        subproblem_solver_options = {}
    if route_initial is None:
        route_initial = []
    if obj_route_initial is None:
        obj_route_initial = []

    log = get_logger('dsda')
    if global_tee:
        log.info(f"Starting D-SDA with k={k}")

    route = route_initial
    obj_route = obj_route_initial
    global_evaluated = list(route_initial)
    ext_var = starting_point

    m = model_function(**model_args)
    dict_extvar, num_ext_var, min_allowed, max_allowed = get_external_information(m, ext_dict)
    if len(starting_point) != num_ext_var:
        raise ValueError(f"Initialization vector length {len(starting_point)} != expected {num_ext_var}")

    t_start = time.perf_counter()
    dsda_usertime = 0.0
    if provide_starting_initialization:
        m_init = initialize_model(m, from_feasible=True, feasible_model=feasible_model, json_path=None)
    else:
        m_init = m

    if mip_transformation:
        m_init, dict_extvar = extvars_gdp_to_mip(m=m_init, gdp_dict_extvar=dict_extvar, transformation=transformation)

    m_fixed = external_ref(
        m=m_init,
        x=ext_var,
        extra_logic_function=ext_logic,
        dict_extvar=dict_extvar,
        mip_ref=mip_transformation,
        tee=False,
    )

    m_solved = solve_subproblem(
        m=m_fixed,
        subproblem_solver=subproblem_solver,
        subproblem_solver_options=subproblem_solver_options,
        timelimit=iter_timelimit,
        gams_output=gams_output,
        tee=tee,
        rel_tol=rel_tol,
    )
    dsda_usertime += getattr(m_solved, 'dsda_usertime', 0.0)
    fmin = pe.value(m_solved.obj)
    if global_tee:
        log.info(f"Initializing... Evaluated: {ext_var} | Objective: {round(fmin,5)} | Global Time: {round(time.perf_counter()-t_start,2)}")
        if getattr(m_solved, 'dsda_status', '') in ('FBBT_Infeasible', 'Evaluated_Infeasible'):
            log.warning('Initialization infeasible, attempting neighborhood verification.')

    best_path = generate_initialization(m_solved)
    route.append(ext_var)
    obj_route.append(fmin)
    global_evaluated.append(ext_var)

    if k == '2':
        neighborhood = neighborhood_k_eq_2(len(ext_var))
    elif k == 'Infinity':
        neighborhood = neighborhood_k_eq_inf(len(ext_var))
    elif k == 'L_natural':
        neighborhood = neighborhood_k_eq_l_natural(len(ext_var))
    elif k == 'L_natural_modified':
        neighborhood = neighborhood_k_eq_l_natural_modified(len(ext_var))
    elif k == 'M_natural':
        neighborhood = neighborhood_k_eq_m_natural(len(ext_var))
    elif k == 'all_interactions':
        neighborhood = neighborhood_k_eq_all(len(ext_var))
    else:
        raise ValueError('Invalid neighborhood type')

    if scaling:
        for i in neighborhood.keys():
            neighborhood[i] = list(scale_factor * np.asarray(neighborhood[i]))

    looking_in_neighbors = True
    while looking_in_neighbors:
        if time.perf_counter() - t_start > timelimit:
            break

        neighbors = find_actual_neighbors(ext_var, neighborhood, min_allowed=min_allowed, max_allowed=max_allowed)
        if time.perf_counter() - t_start > timelimit:
            break

        fmin, best_var, best_dir, improve, eval_time, ns_evaluated, best_path = evaluate_neighbors(
            stop_when_improvement_found=stop_neigh_verif_when_improv,
            ext_vars=neighbors,
            fmin=fmin,
            model_function=model_function,
            model_args=model_args,
            ext_dict=dict_extvar,
            ext_logic=ext_logic,
            mip_transformation=mip_transformation,
            transformation=transformation,
            subproblem_solver=subproblem_solver,
            subproblem_solver_options=subproblem_solver_options,
            iter_timelimit=iter_timelimit,
            timelimit=timelimit,
            current_time=t_start,
            gams_output=gams_output,
            tee=tee,
            global_tee=global_tee,
            rel_tol=rel_tol,
            global_evaluated=global_evaluated,
            init_path=best_path,
        )
        dsda_usertime += eval_time
        global_evaluated += ns_evaluated

        if improve:
            route.append(best_var)
            obj_route.append(fmin)
            if global_tee and time.perf_counter() - t_start < timelimit:
                log.info(f"Line search in direction: {neighborhood[best_dir]}")
            line_searching = True
            while line_searching:
                if time.perf_counter() - t_start > timelimit:
                    break
                fmin, best_var, moved, ls_time, ls_evaluated, best_path = do_line_search(
                    start=best_var,
                    fmin=fmin,
                    direction=neighborhood[best_dir],
                    model_function=model_function,
                    model_args=model_args,
                    ext_dict=dict_extvar,
                    ext_logic=ext_logic,
                    mip_transformation=mip_transformation,
                    transformation=transformation,
                    subproblem_solver=subproblem_solver,
                    min_allowed=min_allowed,
                    max_allowed=max_allowed,
                    iter_timelimit=iter_timelimit,
                    timelimit=timelimit,
                    current_time=t_start,
                    gams_output=gams_output,
                    tee=tee,
                    global_tee=global_tee,
                    rel_tol=rel_tol,
                    global_evaluated=global_evaluated,
                    init_path=best_path,
                )
                global_evaluated += ls_evaluated
                dsda_usertime += ls_time
                if time.perf_counter() - t_start > timelimit:
                    break
                if moved:
                    route.append(best_var)
                    obj_route.append(fmin)
                else:
                    ext_var = best_var
                    line_searching = False
                    if global_tee:
                        log.info(f"New best point: {best_var}")
        else:
            looking_in_neighbors = False

    t_end = round(time.perf_counter() - t_start, 2)
    if global_tee:
        log.info(f"D-SDA finished in {t_end}s | Best objective: {round(fmin,5)} | Route length: {len(route)}")

    m2 = model_function(**model_args)
    m2_solved = initialize_model(m2, json_path=best_path)
    return m2_solved, route, obj_route, best_path, dsda_usertime
