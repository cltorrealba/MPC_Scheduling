from __future__ import annotations
import time
from typing import Any, Dict
from biorefinery.scripts.integrate_scheduling_enmpc import run_integration
from biorefinery.scripts.legacy_adapter import run_legacy_single_step

__all__ = ["run_modular","run_legacy_snapshot"]

def run_modular(horizon_h: float, nfe: int, solver: str | None, sched_periods: int):
    class _Args:  # simple namespace
        pass
    a = _Args()
    a.sched_horizon_h = horizon_h
    a.sched_periods = sched_periods
    a.fer_horizon_h = horizon_h
    a.nfe = nfe
    a.solver = solver
    a.cin_scale = 1.0
    a.max_concentration = 200.0
    a.min_hold_up = 100.0
    a.output = None
    a.tee = False
    return run_integration(a)


def run_legacy_snapshot(horizon_h: float, nfe: int, solver: str | None, regularize: bool,
                        floor_M: float | None, floor_C: float | None, warmstart: bool, mass_slack: bool,
                        cap_M: float | None, diagnostics: bool, diagnostics_top: int,
                        initial_mass_slack: bool,
                        feed_align: bool, feed_slack: bool, feed_slack_weight: float,
                        smooth_fin_weight: float, align_modular_init: bool, scale_model: bool,
                        simple_feed: bool, simple_feed_rate: float | None, normalized_feed: bool,
                        normalized_feed_scale: bool,
                        ipopt_max_iter: int | None,
                        ipopt_tol: float | None,
                        ipopt_acceptable_tol: float | None,
                        ipopt_print_level: int | None,
                        normalized_feed_slack: bool,
                        normalized_feed_slack_weight: float,
                        ipopt_linear_solver: str | None,
                        ipopt_bound_relax_factor: float | None,
                        ipopt_constr_viol_tol: float | None,
                        normalized_feed_micro_slack: bool,
                        normalized_feed_micro_slack_budget: float,
                        normalized_feed_micro_slack_weight: float,
                        jitter_conc: bool,
                        jitter_conc_mag: float,
                        jitter_seed: int | None,
                        sync_fin_initial: bool,
                        relax_initial_comp: bool) -> Dict[str, Any]:
    t0 = time.time()
    res = run_legacy_single_step(total_sim_time=horizon_h*3600.0, total_f_elements_t=nfe, n_f_elements_t=nfe,
                                 solver=solver, regularize=regularize, floor_M=floor_M, floor_C=floor_C,
                                 warmstart=warmstart, add_mass_slack=mass_slack, cap_M=cap_M,
                                 diagnostics=diagnostics, diagnostics_top=diagnostics_top,
                                 initial_mass_slack=initial_mass_slack,
                                 feed_align=feed_align, feed_slack=feed_slack, feed_slack_weight=feed_slack_weight,
                                 smooth_fin_weight=smooth_fin_weight, align_modular_init=align_modular_init,
                                 scale_model=scale_model, simple_feed=simple_feed, simple_feed_rate=simple_feed_rate,
                                 normalized_feed=normalized_feed, normalized_feed_scale=normalized_feed_scale,
                                 ipopt_max_iter=ipopt_max_iter, ipopt_tol=ipopt_tol,
                                 ipopt_acceptable_tol=ipopt_acceptable_tol, ipopt_print_level=ipopt_print_level,
                                 normalized_feed_slack=normalized_feed_slack,
                                 normalized_feed_slack_weight=normalized_feed_slack_weight,
                                 ipopt_linear_solver=ipopt_linear_solver,
                                 ipopt_bound_relax_factor=ipopt_bound_relax_factor,
                                 ipopt_constr_viol_tol=ipopt_constr_viol_tol,
                                 normalized_feed_micro_slack=normalized_feed_micro_slack,
                                 normalized_feed_micro_slack_budget=normalized_feed_micro_slack_budget,
                                 normalized_feed_micro_slack_weight=normalized_feed_micro_slack_weight,
                                 jitter_conc=jitter_conc, jitter_conc_mag=jitter_conc_mag, jitter_seed=jitter_seed,
                                 sync_fin_initial=sync_fin_initial,
                                 relax_initial_comp=relax_initial_comp)
    res['elapsed_s'] = time.time() - t0
    return res
