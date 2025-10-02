from __future__ import annotations
import argparse, pathlib, sys, json, math, csv, time, random
from typing import Dict, Any

from biorefinery.metadata import gather_run_metadata
from biorefinery.scripts.integrate_scheduling_enmpc import run_integration

# NOTE: Placeholder: integration currently always starts from model defaults.
# Future work (state handoff) will inject previous final states.

def build_args(horizon_h: float, nfe: int, solver: str | None):
    class _A: pass
    a = _A()
    a.sched_horizon_h = horizon_h
    a.sched_periods = 4  # fixed for now
    a.fer_horizon_h = horizon_h
    a.nfe = nfe
    a.solver = solver
    a.cin_scale = 1.0
    a.max_concentration = 200.0
    a.min_hold_up = 100.0
    a.output = None
    a.tee = False
    return a

CSV_HEADER = [
    'step_index','t_start_h','t_end_h','prediction_h','apply_h','nfe','mod_elapsed_s',
    'predicted_end_h','applied_abs_time_h','propagation_mode','schedule_horizon_h','horizon_gap',
    'final_ethanol_pred','ethanol_applied_pred','final_hold_up_pred','hold_up_applied_pred',
    'productivity_pred','economic_metric','economic_metric2','git_commit','git_dirty','python_version','feasible_flag',
    'schedule_feasible_flag','schedule_obj_value',
    'drift_l2','drift_max_abs','drift_l2_avg','drift_max_abs_avg','drift_l2_cum','drift_max_abs_cum','drift_alert'
]

def write_row(path: pathlib.Path, row: Dict[str, Any]):
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Header rotation if existing header mismatches
    if not new_file:
        try:
            with path.open('r', encoding='utf-8') as fr:
                first_line = fr.readline().strip()
            current_header = first_line.split(',') if first_line else []
            if current_header != CSV_HEADER:
                ts = time.strftime('%Y%m%d_%H%M%S')
                backup = path.parent / f"{path.stem}_old_{ts}{path.suffix}"
                path.replace(backup)
                new_file = True
        except Exception:
            pass
    with path.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new_file:
            w.writeheader()
        w.writerow({k: row.get(k) for k in CSV_HEADER})

def main():
    ap = argparse.ArgumentParser(description='Rolling EMPC prototype loop using modular integration.')
    ap.add_argument('--total-horizon-h', type=float, default=12.0)
    ap.add_argument('--empc-step-h', type=float, default=3.0)
    ap.add_argument('--prediction-horizon-h', type=float, default=6.0)
    ap.add_argument('--nfe-per-h', type=float, default=0.5, help='Discretization density (nfe = ceil(prediction_h * nfe_per_h).')
    ap.add_argument('--solver', default=None)
    ap.add_argument('--log-dir', default='logs/empc_rolling')
    ap.add_argument('--store-json', action='store_true', dest='store_json', help='Store per-step JSON payloads.', default=False)
    ap.add_argument('--warm-start-schedule', action='store_true', help='Reuse previous scheduling batch solution as initial values.')
    ap.add_argument('--schedule-horizon-mode', choices=['prediction','applied'], default='prediction', help='Length of scheduling horizon each step.')
    ap.add_argument('--exec-disturbance-alpha', type=float, default=0.0, help='Execution disturbance factor applied to applied_state concentrations.')
    ap.add_argument('--drift-exclude-holdup', action='store_true', help='Exclude hold-up from drift metrics.')
    ap.add_argument('--seed', type=int, default=None, help='Random seed for disturbances.')
    ap.add_argument('--propagation-mode', choices=['final','applied','realized'], default='final', help='State used as initial condition next step.')
    ap.add_argument('--auto-propagation', action='store_true', help='Override propagation-mode using heuristic (prefer realized if drift small, else final).')
    ap.add_argument('--auto-drift-threshold', type=float, default=0.5, help='L2 drift threshold (g/kg) to accept realized propagation.')
    ap.add_argument('--fermentation-warm-start', action='store_true', help='Warm start fermentation interior points with previous final state.')
    ap.add_argument('--economic-lambda', type=float, default=0.0, help='Penalty per non-zero scheduling batch aggregated for economic metric.')
    ap.add_argument('--export-drift-species', action='store_true', help='Export per-species drift values to a CSV file.')
    ap.add_argument('--economic-lambda2', type=float, default=0.0, help='Secondary penalty weight times average non-zero batch size.')
    ap.add_argument('--feedback-scheduling-mode', choices=['none','ethanol','all_species'], default='none', help='Map previous fermentation state to scheduling initial inventory override.')
    ap.add_argument('--feedback-scheduling-scale', type=float, default=1.0, help='Scale factor applied when translating concentrations to inventory overrides.')
    ap.add_argument('--drift-window', type=int, default=3, help='Window size (steps) for rolling average drift metrics.')
    ap.add_argument('--drift-alert-threshold', type=float, default=None, help='If set and drift_l2_avg exceeds threshold, drift_alert=1 else 0.')
    args = ap.parse_args()

    meta = gather_run_metadata({'mode': 'empc_rolling'})

    total_steps = math.ceil(args.total_horizon_h / args.empc_step_h)
    log_dir = pathlib.Path(args.log_dir)
    json_dir = log_dir / 'steps'
    csv_path = log_dir / 'rolling_performance_log.csv'

    t_current = 0.0
    last_state = None
    last_batches = None
    last_final_for_warm = None
    drift_history_l2 = []
    drift_history_max = []
    if args.seed is not None:
        random.seed(args.seed)
    for step in range(total_steps):
        pred_h = args.prediction_horizon_h
        apply_h = min(args.empc_step_h, args.total_horizon_h - t_current)
        if apply_h <= 0:
            break
        # Discretization for this prediction window
        nfe = max(1, math.ceil(pred_h * args.nfe_per_h))
        t0 = time.time()
        # Build args for integration (prediction window only)
        run_args = build_args(pred_h, nfe, args.solver)
        # Optionally shorten scheduling horizon to apply_h
        if args.schedule_horizon_mode == 'applied':
            run_args.sched_horizon_h = apply_h
        capture_fraction = apply_h / pred_h if pred_h > 0 else None
        # Build inventory override for scheduling feedback
        inventory_override = None
        if last_state and args.feedback_scheduling_mode != 'none':
            C_prev = last_state.get('C', {})
            inventory_override = {}
            if args.feedback_scheduling_mode == 'ethanol':
                if 'Eth' in C_prev:
                    inventory_override['F'] = C_prev['Eth'] * args.feedback_scheduling_scale
            else:  # all_species
                for sp, val in C_prev.items():
                    # Map species directly if exists in scheduling state set
                    # Scheduling states: G, X, ACT, HMF, F, Cell
                    if sp in ['G','X','ACT','HMF','F','Cell'] and isinstance(val,(int,float)):
                        inventory_override[sp] = val * args.feedback_scheduling_scale
        result = run_integration(
            run_args,
            initial_state=last_state,
            start_time_h=t_current,
            capture_fraction=capture_fraction,
            previous_batches=last_batches if args.warm_start_schedule else None,
            fermentation_warm_start=(last_final_for_warm if args.fermentation_warm_start else None),
            inventory_override=inventory_override,
        )
        mod_elapsed = time.time() - t0
        kpis = result.get('kpis', result)
        final_eth = kpis.get('final_ethanol_conc')
        final_hold = kpis.get('final_hold_up')
        applied_state = result.get('applied_state') or {}
        ethanol_applied = None
        hold_up_applied = None
        if applied_state:
            ethanol_applied = applied_state['C'].get('Eth')
            hold_up_applied = applied_state.get('M') or applied_state.get('hold_up')
        productivity = None
        if final_eth is not None and pred_h > 0:
            try:
                productivity = final_eth / pred_h
            except Exception:
                productivity = None
        # fermentation_status lives inside kpis
        ferm_status = kpis.get('fermentation_status') or result.get('fermentation_status')
        feasible_flag = int(ferm_status == 'optimal')
        predicted_end_h = (result.get('final_state') or {}).get('abs_final_time_h', t_current + pred_h)
        # Gather candidate states for later propagation decision
        final_state_full = result.get('final_state')
        applied_state_full = result.get('applied_state')
        realized_state = (applied_state_full or {}).get('realized') if applied_state_full else None
        propagation_mode = args.propagation_mode

        # Drift metrics: compare predicted applied_state vs realized with disturbance
        drift_l2 = None
        drift_max = None
        if applied_state and args.exec_disturbance_alpha > 0:
            realized = json.loads(json.dumps(applied_state))  # deep copy
            alpha = args.exec_disturbance_alpha
            species = list(applied_state['C'].keys())
            diffs = []
            for sp in species:
                if sp not in realized['C']:
                    continue
                base = realized['C'][sp]
                # Only perturb concentrations that aren't large placeholder values (heuristic: skip if > 500)
                if isinstance(base, (int,float)) and base < 500:
                    perturb = base * (1 + (random.uniform(-alpha, alpha)))
                    realized['C'][sp] = perturb
            # Drift calculation
            for sp in species:
                if sp == 'M':
                    continue
                pred_val = applied_state['C'][sp]
                real_val = realized['C'][sp]
                if pred_val is None or real_val is None:
                    continue
                diffs.append(real_val - pred_val)
            # Optionally include hold-up unless excluded
            if not args.drift_exclude_holdup:
                m_pred = applied_state.get('M')
                m_real = realized.get('M', m_pred)
                if m_pred is not None and m_real is not None:
                    diffs.append(m_real - m_pred)
            if diffs:
                drift_l2 = math.sqrt(sum(d*d for d in diffs))
                drift_max = max(abs(d) for d in diffs)
            # Optionally record realized into JSON output row extension
            applied_state['realized'] = realized
        else:
            drift_l2 = 0.0 if applied_state else None
            drift_max = 0.0 if applied_state else None
        # Auto propagation decision (after drift computed)
        if args.auto_propagation and applied_state and drift_l2 is not None:
            # Heuristic: if drift small -> realized (if available), else final
            if drift_l2 <= args.auto_drift_threshold and realized_state:
                propagation_mode = 'realized'
            else:
                propagation_mode = 'final'
        # Assign last_state based on (possibly updated) propagation_mode
        if propagation_mode == 'final':
            last_state = final_state_full
        elif propagation_mode == 'applied':
            if applied_state_full:
                last_state = {
                    'C': applied_state_full.get('C', {}),
                    'M': applied_state_full.get('M'),
                    'abs_final_time_h': applied_state_full.get('abs_time_h')
                }
            else:
                last_state = final_state_full
        else:  # realized
            if realized_state:
                last_state = {
                    'C': realized_state.get('C', {}),
                    'M': realized_state.get('M'),
                    'abs_final_time_h': (applied_state_full or {}).get('abs_time_h')
                }
            else:
                last_state = final_state_full
        last_batches = (result.get('scheduling') or {}).get('batches')
        last_final_for_warm = last_state  # after propagation decision

        # Economic metric: ethanol_applied_pred / apply_h - lambda * num_batches (non-zero)
        econ_metric = None
        if ethanol_applied is not None and apply_h > 0:
            try:
                nbatches = 0
                if last_batches:
                    nbatches = sum(1 for v in last_batches.values() if abs(v) > 1e-12)
                econ_metric = (ethanol_applied / apply_h) - args.economic_lambda * nbatches
            except Exception:
                econ_metric = None
        schedule_horizon_h = run_args.sched_horizon_h
        schedule_status = (result.get('kpis') or {}).get('scheduling_status')
        schedule_feasible_flag = int(schedule_status == 'optimal') if schedule_status else None
        schedule_obj_value = (result.get('scheduling') or {}).get('objective_value')
        horizon_gap = pred_h - schedule_horizon_h
        # Extended economic_metric2
        econ_metric2 = None
        if ethanol_applied is not None and apply_h > 0:
            try:
                nbatches_vals = []
                if last_batches:
                    nbatches_vals = [v for v in last_batches.values() if abs(v) > 1e-12]
                nbatches = len(nbatches_vals)
                avg_batch = sum(nbatches_vals)/nbatches if nbatches>0 else 0.0
                econ_metric2 = (ethanol_applied / apply_h) - args.economic_lambda * nbatches - args.economic_lambda2 * avg_batch
            except Exception:
                econ_metric2 = None
        # Update drift histories
        if drift_l2 is not None:
            drift_history_l2.append(drift_l2)
            drift_history_max.append(drift_max)
        window = args.drift_window if args.drift_window and args.drift_window>0 else 1
        drift_l2_avg = None
        drift_max_avg = None
        if drift_history_l2:
            recent_l2 = drift_history_l2[-window:]
            recent_max = drift_history_max[-window:]
            drift_l2_avg = sum(recent_l2)/len(recent_l2)
            drift_max_avg = sum(recent_max)/len(recent_max)
        drift_l2_cum = sum(drift_history_l2) if drift_history_l2 else None
        drift_max_cum = sum(drift_history_max) if drift_history_max else None
        drift_alert = None
        if args.drift_alert_threshold is not None and drift_l2_avg is not None:
            drift_alert = int(drift_l2_avg > args.drift_alert_threshold)
        row = {
            'step_index': step,
            't_start_h': t_current,
            't_end_h': t_current + apply_h,
            'prediction_h': pred_h,
            'apply_h': apply_h,
            'nfe': nfe,
            'mod_elapsed_s': mod_elapsed,
            'predicted_end_h': predicted_end_h,
            'propagation_mode': propagation_mode,
            'schedule_horizon_h': schedule_horizon_h,
            'horizon_gap': horizon_gap,
            'final_ethanol_pred': final_eth,
            'ethanol_applied_pred': ethanol_applied,
            'final_hold_up_pred': final_hold,
            'hold_up_applied_pred': hold_up_applied,
            'productivity_pred': productivity,
            'economic_metric': econ_metric,
            'economic_metric2': econ_metric2,
            'git_commit': meta.get('git_commit'),
            'git_dirty': meta.get('git_dirty'),
            'python_version': meta.get('python_version'),
            'feasible_flag': feasible_flag,
            'schedule_feasible_flag': schedule_feasible_flag,
            'schedule_obj_value': schedule_obj_value,
            'applied_abs_time_h': (applied_state or {}).get('abs_time_h'),
            'drift_l2': drift_l2,
            'drift_max_abs': drift_max,
            'drift_l2_avg': drift_l2_avg,
            'drift_max_abs_avg': drift_max_avg,
            'drift_l2_cum': drift_l2_cum,
            'drift_max_abs_cum': drift_max_cum,
            'drift_alert': drift_alert,
        }
        write_row(csv_path, row)
        if args.store_json:
            json_dir.mkdir(parents=True, exist_ok=True)
            with (json_dir / f'step_{step:03d}.json').open('w', encoding='utf-8') as jf:
                json.dump({'meta': meta, 'step_row': row, 'raw': result}, jf, indent=2)
        # Species drift export
        if args.export_drift_species and applied_state and 'realized' in applied_state:
            drift_path = log_dir / 'drift_species_log.csv'
            new_file = not drift_path.exists()
            species = sorted(applied_state['C'].keys())
            with drift_path.open('a', newline='', encoding='utf-8') as df:
                writer = csv.writer(df)
                if new_file:
                    writer.writerow(['step_index','mode'] + species)
                row_vals = [step, propagation_mode]
                for sp in species:
                    pred_val = applied_state['C'][sp]
                    real_val = applied_state['realized']['C'][sp]
                    row_vals.append(real_val - pred_val)
                writer.writerow(row_vals)
        t_current += apply_h
        if t_current >= args.total_horizon_h:
            break
    print(f'Rolling EMPC completed. CSV at {csv_path}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
