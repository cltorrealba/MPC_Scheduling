"""Solver and preprocessing utilities extracted from legacy script."""
from __future__ import annotations
import os
import time
import pyomo.environ as pe
from pyomo.common.errors import InfeasibleConstraintException
from pyomo.opt.base.solvers import SolverFactory
from typing import Optional

def _has_discrete_vars(m):
    for v in m.component_data_objects(pe.Var, descend_into=True):
        if v.is_binary() or v.is_integer():
            return True
    return False


def preprocess_problem(m, simple: bool = True):
    if not simple:
        pe.TransformationFactory('contrib.detect_fixed_vars').apply_to(m)
        pe.TransformationFactory('contrib.propagate_fixed_vars').apply_to(m)
        pe.TransformationFactory('contrib.remove_zero_terms').apply_to(m)
        pe.TransformationFactory('contrib.propagate_zero_sum').apply_to(m)
        pe.TransformationFactory('contrib.constraints_to_var_bounds').apply_to(m)
        pe.TransformationFactory('contrib.detect_fixed_vars').apply_to(m)
        pe.TransformationFactory('contrib.propagate_zero_sum').apply_to(m)
        pe.TransformationFactory('contrib.deactivate_trivial_constraints').apply_to(m, tmp=False, ignore_infeasible=True)


def solve_subproblem(m, subproblem_solver='conopt4', subproblem_solver_options=None,
                     timelimit=1000, gams_output=False, tee=False, rel_tol=0,
                     allow_fallback: bool = True):
    if subproblem_solver_options is None:
        subproblem_solver_options = {}
    m.dsda_status = 'Initialized'
    m.dsda_usertime = 0
    start_prep = time.time()
    try:
        preprocess_problem(m, simple=True)
    except InfeasibleConstraintException:
        m.dsda_status = 'FBBT_Infeasible'
        return m
    end_prep = time.time()
    m.dsda_usertime += (end_prep - start_prep)

    output_options = {}
    if gams_output:
        dir_path = os.path.dirname(os.path.abspath(__file__))
        gams_path = os.path.join(dir_path, "gamsfiles/")
        if not (os.path.exists(gams_path)):
            os.makedirs(gams_path)
        output_options = {'keepfiles': True, 'tmpdir': gams_path, 'symbolic_solver_labels': True}

    used_gams = False
    opt = None
    # First attempt: GAMS interface
    try:
        solvername = 'gams'
        if subproblem_solver_options is not None:
            subproblem_solver_options.setdefault('add_options', [])
            subproblem_solver_options['add_options'].append(f'option reslim={timelimit};')
            subproblem_solver_options['add_options'].append(f'option optcr={rel_tol};')
        if subproblem_solver.lower() == 'octeract':
            opt = SolverFactory(solvername)
        else:
            opt = SolverFactory(solvername, solver=subproblem_solver)
        if opt is None or not opt.available(False):
            raise RuntimeError('GAMS interface or solver not available')
        used_gams = True
    except Exception:
        opt = None

    # Second attempt: direct solver (non-GAMS) if GAMS failed
    if opt is None:
        try:
            opt = SolverFactory(subproblem_solver)
            if opt is None or not opt.available(False):
                raise RuntimeError('Direct solver not available')
        except Exception:
            opt = None

    # Fallback to ipopt if allowed and problem is continuous
    if opt is None and allow_fallback:
        if not _has_discrete_vars(m):
            try:
                ipopt_opt = SolverFactory('ipopt')
                if ipopt_opt is not None and ipopt_opt.available(False):
                    opt = ipopt_opt
                    subproblem_solver = 'ipopt'
            except Exception:
                pass

    if opt is None:
        m.dsda_status = 'Solver_Not_Available'
        return m

    # Adjust solve kwargs depending on interface
    solve_kwargs = {}
    if used_gams:
        solve_kwargs.update(output_options)
        if subproblem_solver_options is not None:
            solve_kwargs.update(subproblem_solver_options)
        m.results = opt.solve(m, tee=tee, skip_trivial_constraints=True, **solve_kwargs)
    else:
        # Non-GAMS: emulate time limit if possible via suffix or ignore
        try:
            m.results = opt.solve(m, tee=tee)
        except Exception as exc:
            m.dsda_status = 'Solve_Failed'
            return m
    # user_time may not exist outside GAMS; guard
        ut = getattr(m.results.solver, 'user_time', 0.0)
        try:
            m.dsda_usertime += float(ut)
        except Exception:
            pass

    term = str(m.results.solver.termination_condition)
    infeas_terms = {'infeasible', 'other', 'unbounded', 'invalidProblem', 'solverFailure', 'internalSolverError', 'error', 'resourceInterrupt', 'licensingProblem', 'noSolution', 'intermediateNonInteger'}
    if term in infeas_terms:
        m.dsda_status = 'Evaluated_Infeasible'
        try:
            m.obj.value = 1000000
        except Exception:
            pass
    else:
        m.dsda_status = 'Optimal'
    return m


def pick_available_solver(candidates=None, return_options=False):
    """Return first available solver from candidate list.

    Parameters
    ----------
    candidates : list[(name, options_dict)] or None
        Default order if None: ipopt, gams(conopt), bonmin, scip.
    return_options : bool
        If True return (name, options_dict) else name.
    """
    default = [
        ('ipopt', {}),
        ('gams', {'solver': 'conopt'}),
        ('bonmin', {}),
        ('couenne', {}),
        ('scip', {}),
        ('highs', {}),  # útil para MILP si se generan reformulaciones lineales
    ]
    cand = candidates or default
    for name, opts in cand:
        try:
            sf = pe.SolverFactory(name)
            if sf is not None and sf.available(False):
                return (name, opts) if return_options else name
        except Exception:
            continue
    return (None, None) if return_options else None

__all__ = [
    'solve_subproblem',
    'pick_available_solver',
]
