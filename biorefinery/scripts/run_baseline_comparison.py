from __future__ import annotations
import json, subprocess, sys, pathlib, shlex, argparse
# Attempt to import reporting utilities; adjust sys.path or provide fallbacks if unavailable.
try:
    from biorefinery.reporting import summarize_kpis, write_csv_row
except ImportError:
    # Insert the project root (parent of the 'biorefinery' package) instead of the package dir itself.
    package_dir = pathlib.Path(__file__).resolve().parent.parent  # .../biorefinery
    project_root = package_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from biorefinery.reporting import summarize_kpis, write_csv_row  # retry after path injection
    except ImportError:
        def summarize_kpis(data):  # minimal fallback to avoid runtime failure
            return {}
        def write_csv_row(row, path, append=True):
            print(f"Warning: biorefinery.reporting not available; skipping CSV write to {path}", file=sys.stderr)

CFG_PATH = pathlib.Path(__file__).resolve().parent.parent / 'configs' / 'baseline_compare_legacy_modular.json'

def parse_args():
    ap = argparse.ArgumentParser(description='Run baseline modular vs legacy comparison and log KPIs.')
    ap.add_argument('--log-dir', default=None, help='Directory for outputs (JSON + performance_log.csv).')
    return ap.parse_args()

def main():
    args = parse_args()
    if not CFG_PATH.exists():
        print(f"Config file not found: {CFG_PATH}", file=sys.stderr)
        return 1
    cfg = json.loads(CFG_PATH.read_text(encoding='utf-8'))
    horizon = cfg.get('horizon_h', 12.0)
    nfe = cfg.get('nfe', 4)
    periods = cfg.get('sched_periods', 4)
    flags = cfg.get('flags', [])
    # Determine output paths
    if args.log_dir:
        base = pathlib.Path(args.log_dir)
        base.mkdir(parents=True, exist_ok=True)
        out_json = base / 'compare_modular_legacy_baseline.json'
        csv_path = base / 'performance_log.csv'
    else:
        out_json = pathlib.Path('compare_modular_legacy_baseline.json')
        csv_path = pathlib.Path('reporting/performance_log.csv')
    cmd = [sys.executable, '-m', 'biorefinery.scripts.compare_legacy_vs_modular', '--horizon-h', str(horizon), '--nfe', str(nfe), '--sched-periods', str(periods), '--output', str(out_json)]
    cmd.extend(flags)
    print('Running baseline comparison:\n  ' + ' '.join(shlex.quote(c) for c in cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)
    print('STDOUT:\n' + res.stdout)
    if res.stderr:
        print('STDERR:\n' + res.stderr, file=sys.stderr)
    if res.returncode != 0:
        print(f"Process exited with code {res.returncode}", file=sys.stderr)
        return res.returncode
    if out_json.exists():
        data = json.loads(out_json.read_text(encoding='utf-8'))
        k_mod = data.get('modular', {}).get('kpis') or data.get('modular', {})
        legacy = data.get('legacy', {})
        print('\nBaseline KPI Snapshot:')
        print('  Modular final ethanol:', k_mod.get('final_ethanol_conc'))
        print('  Legacy final ethanol :', legacy.get('final_ethanol_conc'))
        print('  Modular hold-up      :', k_mod.get('final_hold_up'))
        print('  Legacy hold-up       :', legacy.get('final_hold_up'))
        print('  Legacy status        :', legacy.get('termination_condition'))
        # Log to performance CSV
        row = summarize_kpis(data)
        write_csv_row(row, csv_path, append=True)
        print(f'Appended row to {csv_path}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
