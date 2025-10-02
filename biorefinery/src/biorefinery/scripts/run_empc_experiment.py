from __future__ import annotations
import argparse, subprocess, sys, json, pathlib, csv, math

from datetime import datetime


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None

def compute_summary(csv_path: pathlib.Path):
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        return {}
    def col(name):
        return [safe_float(r.get(name)) for r in rows if r.get(name) not in (None,'')]
    drift_l2 = col('drift_l2')
    drift_l2_avg = col('drift_l2_avg')
    econ = col('economic_metric2') or col('economic_metric')
    econ = [e for e in econ if e is not None]
    def stats(vals):
        if not vals:
            return {}
        return {
            'mean': sum(vals)/len(vals),
            'max': max(vals),
            'min': min(vals),
            'last': vals[-1],
        }
    return {
        'n_steps': len(rows),
        'drift_l2_stats': stats(drift_l2),
        'drift_l2_avg_stats': stats(drift_l2_avg),
        'economic_metric_stats': stats(econ),
        'final_propagation_mode': rows[-1].get('propagation_mode'),
    }

def build_parser():
    p = argparse.ArgumentParser(description='High-level EMPC experiment wrapper')
    p.add_argument('--log-dir', default='logs/exp_empc')
    p.add_argument('--total-h', type=float, default=12)
    p.add_argument('--step-h', type=float, default=3)
    p.add_argument('--pred-h', type=float, default=6)
    p.add_argument('--nfe-per-h', type=float, default=0.5)
    p.add_argument('--seed', type=int, default=111)
    p.add_argument('--disturb', type=float, default=0.05)
    p.add_argument('--auto', action='store_true', help='Enable auto propagation mode heuristic')
    p.add_argument('--feedback', choices=['none','ethanol','all_species'], default='all_species')
    p.add_argument('--plots', action='store_true', help='Generate PNG plots in log-dir')
    p.add_argument('--econ-lambda', type=float, default=0.1)
    p.add_argument('--econ-lambda2', type=float, default=0.05)
    return p


def main():
    args = build_parser().parse_args()
    log_dir = pathlib.Path(args.log_dir)
    if log_dir.exists():
        # Simple purge for reproducibility
        for p in log_dir.rglob('*'):
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
    log_dir.mkdir(parents=True, exist_ok=True)
    rolling_script = 'biorefinery/src/biorefinery/scripts/run_empc_rolling.py'
    cmd = [
        sys.executable, rolling_script,
        '--total-horizon-h', str(args.total_h),
        '--empc-step-h', str(args.step_h),
        '--prediction-horizon-h', str(args.pred_h),
        '--nfe-per-h', str(args.nfe_per_h),
        '--log-dir', str(log_dir),
        '--exec-disturbance-alpha', str(args.disturb),
        '--seed', str(args.seed),
        '--economic-lambda', str(args.econ_lambda),
        '--economic-lambda2', str(args.econ_lambda2),
        '--export-drift-species', '--warm-start-schedule', '--fermentation-warm-start', '--store-json',
        '--feedback-scheduling-mode', args.feedback,
        '--drift-window', '3', '--drift-alert-threshold', '0.5'
    ]
    if args.auto:
        cmd.append('--auto-propagation')
    print('Running rolling EMPC...')
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr)
        raise SystemExit('Rolling EMPC failed')
    csv_path = log_dir/'rolling_performance_log.csv'
    if not csv_path.exists():
        raise SystemExit('Missing CSV output')
    summary = compute_summary(csv_path)
    summary['timestamp'] = datetime.utcnow().isoformat()
    summary_path = log_dir/'summary.json'
    with summary_path.open('w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print('Summary:', json.dumps(summary, indent=2))
    # Optional plots
    if args.plots:
        plot_script = 'biorefinery/src/biorefinery/scripts/plot_empc_results.py'
        png_main = log_dir/'empc_overview.png'
        subprocess.run([sys.executable, plot_script, '--csv', str(csv_path), '--output', str(png_main)])
        print('Plot saved at', png_main)
    return 0

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
