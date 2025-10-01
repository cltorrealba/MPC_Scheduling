from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, shlex

# Attempt import; fallback to injecting project root for direct execution scenarios
try:
    from biorefinery.reporting import load_comparison, summarize_kpis, write_csv_row
except ImportError:
    project_root = pathlib.Path(__file__).resolve().parent.parent  # .../biorefinery
    project_root = project_root.parent  # repo root
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    try:
        from biorefinery.reporting import load_comparison, summarize_kpis, write_csv_row  # type: ignore
    except ImportError:
        def load_comparison(p):
            with open(p,'r',encoding='utf-8') as f: return json.load(f)
        def summarize_kpis(payload): return {}
        def write_csv_row(row, path, append=True):
            print(f"Warning: biorefinery.reporting unavailable; skipping CSV append to {path}", file=sys.stderr)


def run_one(h: float, nfe: int, periods: int, extra_flags: list[str], out_dir: pathlib.Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"compare_h{int(h)}.json"
    cmd = [sys.executable, '-m', 'biorefinery.scripts.compare_legacy_vs_modular', '--horizon-h', str(h), '--nfe', str(nfe), '--sched-periods', str(periods), '--output', str(out_json)]
    cmd.extend(extra_flags)
    print('RUN', ' '.join(shlex.quote(c) for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print('STDERR:', r.stderr)
        raise SystemExit(f"Failed run horizon {h}")
    payload = load_comparison(out_json)
    return payload


def main():
    ap = argparse.ArgumentParser(description='Run multi-horizon modular vs legacy comparisons and log KPIs.')
    ap.add_argument('--horizons', type=float, nargs='*', default=[12,24,48])
    ap.add_argument('--nfe', type=int, default=4)
    ap.add_argument('--sched-periods', type=int, default=4)
    ap.add_argument('--out-dir', default='multi_horizon_outputs')
    ap.add_argument('--csv', default='reporting/performance_log.csv')
    ap.add_argument('--legacy-stable-flags', action='store_true', help='Include known stable legacy flags baseline set.')
    args = ap.parse_args()

    flags: list[str] = []
    if args.legacy_stable_flags:
        flags.extend([
            '--legacy-normalized-feed',
            '--legacy-normalized-feed-scale',
            '--legacy-initial-mass-slack',
            '--legacy-relax-initial-comp',
            '--legacy-regularize',
            '--legacy-floor-C','1e-4'
        ])

    out_dir = pathlib.Path(args.out_dir)
    csv_path = pathlib.Path(args.csv)

    for h in args.horizons:
        payload = run_one(h, args.nfe, args.sched_periods, flags, out_dir)
        row = summarize_kpis(payload)
        write_csv_row(row, csv_path, append=True)
        print('Logged horizon', h)

    print('Done. CSV at', csv_path)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
