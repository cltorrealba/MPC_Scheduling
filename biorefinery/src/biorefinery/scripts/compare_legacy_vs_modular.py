"""Compare legacy monolithic fermentation scheduling/control vs modular integration prototype.

Workflow:
 1. Run modular pipeline (scheduling minimal + fermentation) via in-process call (imports integrate_scheduling_enmpc.run_integration).
 2. Run legacy single-horizon fermentation builder (if available) to approximate comparable KPIs.
 3. Collect KPIs: final ethanol concentration, final hold-up, solver status.
 4. Emit JSON with absolute and relative deltas.

Notes:
 - Legacy script Fermentation_Scheduling_and_MPC.py is large; we avoid executing full DSDA routines.
 - We attempt to import build_fermentation_one_time_step_new; if missing or fails, legacy section marks status 'unavailable'.
 - Future: add cost, batch utilization, route activation diff, timing metrics.

Usage:
  python -m biorefinery.scripts.compare_legacy_vs_modular --output compare.json
"""
from __future__ import annotations
import argparse, json, time
from biorefinery.scripts.comparison_helpers import run_modular, run_legacy_snapshot




def compare(args):
    # Modular run with timing
    t0_mod = time.time()
    mod = run_modular(args.horizon_h, args.nfe, args.solver, args.sched_periods)
    mod_elapsed = time.time() - t0_mod
    # Legacy run
    legacy = run_legacy_snapshot(args.horizon_h, args.nfe, args.solver, args.legacy_regularize,
                                 args.legacy_floor_M, args.legacy_floor_C, args.legacy_warmstart, args.legacy_mass_slack,
                                 args.legacy_cap_M, args.legacy_diagnostics, args.legacy_diagnostics_top,
                                 args.legacy_initial_mass_slack,
                                 args.legacy_feed_align, args.legacy_feed_slack, args.legacy_feed_slack_weight,
                                 args.legacy_smooth_fin_weight, args.legacy_align_modular_init, args.legacy_scale_model,
                                 args.legacy_simple_feed, args.legacy_simple_feed_rate, args.legacy_normalized_feed,
                                 args.legacy_normalized_feed_scale, args.legacy_ipopt_max_iter,
                                 args.legacy_ipopt_tol, args.legacy_ipopt_acceptable_tol, args.legacy_ipopt_print_level,
                                 args.legacy_normalized_feed_slack, args.legacy_normalized_feed_slack_weight,
                                 args.legacy_ipopt_linear_solver, args.legacy_ipopt_bound_relax_factor, args.legacy_ipopt_constr_viol_tol,
                                 args.legacy_normalized_feed_micro_slack, args.legacy_normalized_feed_micro_slack_budget,
                                 args.legacy_normalized_feed_micro_slack_weight,
                                 args.legacy_jitter_conc, args.legacy_jitter_conc_mag, args.legacy_jitter_seed,
                                 args.legacy_sync_fin_initial,
                                 args.legacy_relax_initial_comp)
    # KPIs extraction
    mod_eth = mod['kpis'].get('final_ethanol_conc')
    mod_M = mod['kpis'].get('final_hold_up')
    leg_eth = legacy.get('final_ethanol_conc')
    leg_M = legacy.get('final_hold_up')
    def _delta(a,b):
        if a is None or b is None:
            return None
        try:
            return a - b
        except Exception:
            return None
    def _reld(a,b):
        if a is None or b is None or abs(b) < 1e-12:
            return None
        return (a - b) / b
    comp = {
        'ethanol_conc_delta': _delta(mod_eth, leg_eth),
        'ethanol_conc_rel': _reld(mod_eth, leg_eth),
        'hold_up_delta': _delta(mod_M, leg_M),
        'hold_up_rel': _reld(mod_M, leg_M),
    }
    payload = {
        'meta': {
            'horizon_h': args.horizon_h,
            'nfe': args.nfe,
            'sched_periods': args.sched_periods,
            'modular_elapsed_s': mod_elapsed,
        },
        'modular': mod['kpis'],
        'legacy': legacy,
        'comparison': comp,
    }
    if args.output:
        with open(args.output,'w',encoding='utf-8') as f:
            json.dump(payload,f,indent=2)
    return payload


def parse_args():
    p = argparse.ArgumentParser(description='Compare legacy single-step fermentation vs modular scheduling+fermentation pipeline')
    p.add_argument('--horizon-h', type=float, default=12.0)
    p.add_argument('--nfe', type=int, default=2)
    p.add_argument('--sched-periods', type=int, default=4)
    p.add_argument('--solver', default=None)
    p.add_argument('--output', default='compare_modular_legacy.json')
    p.add_argument('--legacy-regularize', action='store_true', dest='legacy_regularize', help='Apply epsilon & exponent clamp regularization to legacy model.')
    p.add_argument('--legacy-floor-M', type=float, default=None, dest='legacy_floor_M', help='Lower bound floor for legacy hold-up M.')
    p.add_argument('--legacy-floor-C', type=float, default=None, dest='legacy_floor_C', help='Lower bound floor for legacy concentrations C.')
    p.add_argument('--legacy-warmstart', action='store_true', dest='legacy_warmstart', help='Warm start legacy model via 1-element preliminary solve.')
    p.add_argument('--legacy-mass-slack', action='store_true', dest='legacy_mass_slack', help='Add quadratic slack to mass balance (Diff_mass).')
    p.add_argument('--legacy-cap-M', type=float, default=None, dest='legacy_cap_M', help='Upper bound cap for legacy hold-up M.')
    p.add_argument('--legacy-diagnostics', action='store_true', dest='legacy_diagnostics', help='Collect top-N constraint residual violations for legacy model.')
    p.add_argument('--legacy-diagnostics-top', type=int, default=10, dest='legacy_diagnostics_top', help='Number of top violating constraints to report.')
    p.add_argument('--legacy-initial-mass-slack', action='store_true', dest='legacy_initial_mass_slack', help='Relax only initial mass balance with quadratic penalty.')
    p.add_argument('--legacy-feed-align', action='store_true', dest='legacy_feed_align', help='Rebuild feed constraint as Fin=sum(flows).')
    p.add_argument('--legacy-feed-slack', action='store_true', dest='legacy_feed_slack', help='Add slack to feed balance (after alignment if enabled).')
    p.add_argument('--legacy-feed-slack-weight', type=float, default=1e5, dest='legacy_feed_slack_weight', help='Quadratic penalty weight for feed slack.')
    p.add_argument('--legacy-smooth-fin-weight', type=float, default=0.0, dest='legacy_smooth_fin_weight', help='Weight for Fin smoothing term (sum (Fin_t - Fin_{t-1})^2).')
    p.add_argument('--legacy-align-modular-init', action='store_true', dest='legacy_align_modular_init', help='Seed legacy state variables with modular-like initial guesses.')
    p.add_argument('--legacy-scale-model', action='store_true', dest='legacy_scale_model', help='Apply basic scaling factors to legacy model variables.')
    p.add_argument('--legacy-simple-feed', action='store_true', dest='legacy_simple_feed', help='Override legacy phase logic with simple Fin=0 pattern (diagnostic).')
    p.add_argument('--legacy-simple-feed-rate', type=float, default=None, dest='legacy_simple_feed_rate', help='If set with --legacy-simple-feed, fixes Fin[t] to this constant value (kg/s).')
    p.add_argument('--legacy-normalized-feed', action='store_true', dest='legacy_normalized_feed', help='Rebuild feed constraint using normalized time fractions (10/190,70/190) independent of horizon length.')
    p.add_argument('--legacy-normalized-feed-scale', action='store_true', dest='legacy_normalized_feed_scale', help='Scale constituent feed flows by (horizon/190h) under normalized feed logic.')
    p.add_argument('--legacy-normalized-feed-slack', action='store_true', dest='legacy_normalized_feed_slack', help='Add quadratic slack to normalized feed constraint.')
    p.add_argument('--legacy-normalized-feed-slack-weight', type=float, default=1e6, dest='legacy_normalized_feed_slack_weight', help='Penalty weight for normalized feed slack.')
    p.add_argument('--legacy-normalized-feed-micro-slack', action='store_true', dest='legacy_normalized_feed_micro_slack', help='Enable punctual micro slack (budgeted) on normalized feed constraint (mutually exclusive with distributed slack).')
    p.add_argument('--legacy-normalized-feed-micro-slack-budget', type=float, default=0.01, dest='legacy_normalized_feed_micro_slack_budget', help='Total L1 budget (sum |slack_t|) for micro slack puntual.')
    p.add_argument('--legacy-normalized-feed-micro-slack-weight', type=float, default=1e8, dest='legacy_normalized_feed_micro_slack_weight', help='Quadratic penalty weight for micro slack puntual usage.')
    p.add_argument('--legacy-sync-fin-initial', action='store_true', dest='legacy_sync_fin_initial', help='Synchronize initial Fin guesses to normalized feed expression.')
    p.add_argument('--legacy-ipopt-max-iter', type=int, default=None, dest='legacy_ipopt_max_iter', help='Override Ipopt max_iter for legacy model.')
    p.add_argument('--legacy-ipopt-tol', type=float, default=None, dest='legacy_ipopt_tol', help='Override Ipopt tol (optimality tolerance).')
    p.add_argument('--legacy-ipopt-acceptable-tol', type=float, default=None, dest='legacy_ipopt_acceptable_tol', help='Override Ipopt acceptable_tol.')
    p.add_argument('--legacy-ipopt-print-level', type=int, default=None, dest='legacy_ipopt_print_level', help='Override Ipopt print_level (0-12).')
    p.add_argument('--legacy-ipopt-linear-solver', type=str, default=None, dest='legacy_ipopt_linear_solver', help='Ipopt linear_solver option (e.g., mumps).')
    p.add_argument('--legacy-ipopt-bound-relax-factor', type=float, default=None, dest='legacy_ipopt_bound_relax_factor', help='Ipopt bound_relax_factor option.')
    p.add_argument('--legacy-ipopt-constr-viol-tol', type=float, default=None, dest='legacy_ipopt_constr_viol_tol', help='Ipopt constr_viol_tol option.')
    p.add_argument('--legacy-jitter-conc', action='store_true', dest='legacy_jitter_conc', help='Add small random jitter to interior concentration initial guesses.')
    p.add_argument('--legacy-jitter-conc-mag', type=float, default=1e-5, dest='legacy_jitter_conc_mag', help='Relative magnitude of jitter (multiplied by max(|C|,1)).')
    p.add_argument('--legacy-jitter-seed', type=int, default=None, dest='legacy_jitter_seed', help='Random seed for concentration jitter.')
    p.add_argument('--legacy-relax-initial-comp', action='store_true', dest='legacy_relax_initial_comp', help='Replace initial Diff_comp constraints with direct initial condition equalities (eliminate potential degeneracy).')
    return p.parse_args()


def main():
    args = parse_args()
    res = compare(args)
    print(json.dumps({'summary': {
        'legacy_status': res['legacy'].get('status'),
        'modular_status': res['modular'].get('fermentation_status'),
        'ethanol_delta': res['comparison']['ethanol_conc_delta'],
        'hold_up_delta': res['comparison']['hold_up_delta'],
    }}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
