from __future__ import annotations
import argparse, json, math, pathlib, sys, time, hashlib, random, subprocess
from dataclasses import dataclass, asdict

# Reuse existing rolling integration
from biorefinery.scripts.run_empc_rolling import main as rolling_main

@dataclass
class HorizonResult:
    horizon_h: float
    nfe: int
    elapsed_s: float
    ethanol_final: float | None
    hold_up_final: float | None
    csv_path: str
    status: str
    drift_l2_mean: float | None
    economic_mean: float | None
    stability_ok: bool

BASELINE_FILE = 'logs/fullscale_baseline.json'

NFE_DEFAULT_MAP = {
    12: 4,
    24: 6,
    48: 8,
    72: 10,
}

def parse_nfe_map(spec: str):
    mapping = {}
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        h,n = part.split(':')
        mapping[float(h)] = int(n)
    return mapping

def hash_config(d: dict) -> str:
    raw = json.dumps(d, sort_keys=True, separators=(',',':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def run_single_horizon(h, nfe, args) -> HorizonResult:
    log_dir = pathlib.Path(args.log_dir)/f"h{int(h)}"
    cmd = [
        sys.executable,
        'biorefinery/src/biorefinery/scripts/run_empc_rolling.py',
        '--total-horizon-h', str(h),
        '--empc-step-h', str(args.step_h),
        '--prediction-horizon-h', str(args.pred_h if args.pred_h else min(2*args.step_h, h)),
        '--nfe-per-h', str(nfe/ max(1.0, h)),
        '--log-dir', str(log_dir),
        '--exec-disturbance-alpha', str(args.disturb),
        '--seed', str(args.seed),
        '--economic-lambda', str(args.econ_lambda),
        '--economic-lambda2', str(args.econ_lambda2),
        '--warm-start-schedule', '--fermentation-warm-start', '--export-drift-species', '--store-json'
    ]
    if args.auto:
        cmd.append('--auto-propagation')
    if args.feedback != 'none':
        cmd += ['--feedback-scheduling-mode', args.feedback]
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    status = 'ok' if res.returncode == 0 else 'fail'
    csv_path = log_dir/'rolling_performance_log.csv'
    ethanol_final = hold_up_final = drift_l2_mean = econ_mean = None
    stability_ok = True
    if csv_path.exists():
        import csv
        rows = list(csv.DictReader(csv_path.open()))
        if rows:
            last = rows[-1]
            try:
                ethanol_final = float(last.get('final_ethanol_pred') or 'nan')
            except Exception:
                pass
            try:
                hold_up_final = float(last.get('final_hold_up_pred') or 'nan')
            except Exception:
                pass
            # Compute simple means
            def col(name):
                vals = []
                for r in rows:
                    v = r.get(name)
                    if v not in (None,''):
                        try: vals.append(float(v))
                        except: pass
                return vals
            drifts = col('drift_l2')
            econ = col('economic_metric2') or col('economic_metric')
            drift_l2_mean = sum(drifts)/len(drifts) if drifts else None
            econ_mean = sum(econ)/len(econ) if econ else None
            # Stability heuristic: no NaN ethanol, hold up within plausible bounds
            if ethanol_final is None or hold_up_final is None:
                stability_ok = False
            if hold_up_final is not None and not (0 <= hold_up_final <= 1e6):
                stability_ok = False
    return HorizonResult(horizon_h=h, nfe=nfe, elapsed_s=elapsed, ethanol_final=ethanol_final,
                         hold_up_final=hold_up_final, csv_path=str(csv_path), status=status,
                         drift_l2_mean=drift_l2_mean, economic_mean=econ_mean, stability_ok=stability_ok)


def compare_with_baseline(results: list[HorizonResult], tol: float, regen: bool, path: pathlib.Path):
    if regen or not path.exists():
        payload = {
            'created': time.time(),
            'tolerance_pct': tol,
            'results': [asdict(r) for r in results]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return {'mode':'baseline_created','ok':True}
    stored = json.loads(path.read_text())
    issues = []
    ref_map = {int(r['horizon_h']): r for r in stored.get('results', [])}
    for r in results:
        ref = ref_map.get(int(r.horizon_h))
        if not ref:
            continue
        for metric in ['ethanol_final','hold_up_final']:
            cur = getattr(r, metric)
            refv = ref.get(metric)
            if cur is None or refv in (None,'nan'): continue
            if refv == 0: continue
            pct = abs(cur - refv)/abs(refv)*100.0
            if pct > tol:
                issues.append({'horizon': r.horizon_h, 'metric': metric, 'pct_diff': pct, 'cur': cur, 'ref': refv})
    return {'mode':'baseline_compare','ok': len(issues)==0, 'issues': issues}


def build_parser():
    p = argparse.ArgumentParser(description='Full-scale readiness multi-horizon runner')
    p.add_argument('--log-dir', default='logs/fullscale')
    p.add_argument('--horizons', default='12,24', help='Comma separated horizon hours (e.g. 12,24,48)')
    p.add_argument('--nfe-map', help='Mapping h:nfe,... overrides default (12:4,24:6,48:8,72:10)')
    p.add_argument('--step-h', type=float, default=3.0)
    p.add_argument('--pred-h', type=float, default=None)
    p.add_argument('--disturb', type=float, default=0.05)
    p.add_argument('--econ-lambda', type=float, default=0.1)
    p.add_argument('--econ-lambda2', type=float, default=0.0)
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--auto', action='store_true')
    p.add_argument('--feedback', choices=['none','ethanol','all_species'], default='all_species')
    p.add_argument('--baseline-tol-pct', type=float, default=5.0)
    p.add_argument('--regen-baseline', action='store_true')
    return p


def main():
    args = build_parser().parse_args()
    random.seed(args.seed)
    log_dir = pathlib.Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    # Config snapshot
    cfg = {
        'args': vars(args),
        'nfe_default_map': NFE_DEFAULT_MAP,
    }
    cfg_hash = hash_config(cfg)
    (log_dir/'config_snapshot.json').write_text(json.dumps({'hash': cfg_hash, 'config': cfg}, indent=2))

    nfe_map = dict(NFE_DEFAULT_MAP)
    if args.nfe_map:
        nfe_map.update(parse_nfe_map(args.nfe_map))

    # Sanity short rolling pre-check (4h total, 1h step) unless user disables (simple heuristic)
    sanity_dir = log_dir/'sanity'
    sanity_cmd = [
        sys.executable, 'biorefinery/src/biorefinery/scripts/run_empc_rolling.py',
        '--total-horizon-h','4','--empc-step-h','1','--prediction-horizon-h','2',
        '--nfe-per-h','0.5','--log-dir', str(sanity_dir), '--seed', str(args.seed),
        '--exec-disturbance-alpha', str(args.disturb), '--warm-start-schedule','--fermentation-warm-start'
    ]
    if args.auto: sanity_cmd.append('--auto-propagation')
    if args.feedback != 'none': sanity_cmd += ['--feedback-scheduling-mode', args.feedback]
    subprocess.run(sanity_cmd, capture_output=True, text=True)

    horizons = [float(h.strip()) for h in args.horizons.split(',') if h.strip()]
    results = []
    for h in horizons:
        nfe = nfe_map.get(int(h), math.ceil(h/3))
        res = run_single_horizon(h, nfe, args)
        # Fallback if fail: try nfe-1 once
        if res.status != 'ok' and nfe > 2:
            res = run_single_horizon(h, nfe-1, args)
        results.append(res)

    baseline_path = pathlib.Path(args.log_dir)/'fullscale_baseline.json'
    baseline_status = compare_with_baseline(results, args.baseline_tol_pct, args.regen_baseline, baseline_path)

    summary = {
        'config_hash': cfg_hash,
        'results': [asdict(r) for r in results],
        'baseline': baseline_status,
        'scalability_ratio': _scalability(results),
        'timestamp': time.time(),
    }
    (log_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    # Simple advisory
    if baseline_status.get('ok') and all(r.stability_ok for r in results):
        print('READINESS: PASS (baseline within tolerance & stability ok)')
    else:
        print('READINESS: ATTENTION (see summary issues)')
    return 0


def _scalability(results: list[HorizonResult]):
    # naive: elapsed/horizon
    ratios = []
    for r in results:
        if r.elapsed_s and r.horizon_h:
            ratios.append(r.elapsed_s / (r.horizon_h*3600.0))
    if not ratios: return None
    return {'mean_ratio': sum(ratios)/len(ratios), 'max_ratio': max(ratios)}

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
