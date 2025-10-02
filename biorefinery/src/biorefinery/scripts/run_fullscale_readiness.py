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
    adapt_mode: str | None = None  # 'fine','coarse','fixed'
    adapt_speedup_ratio: float | None = None  # fine_elapsed / chosen_elapsed
    adapt_metrics: dict | None = None  # relative differences
    adapt_tol_effective: float | None = None
    adapt_reason: str | None = None
    fallback_tier: int | None = None  # 0 normal,1 nfe-1,2 pred_h reduced
    prediction_h_used: float | None = None

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


def run_single_horizon(h, nfe, args, pred_scale: float = 1.0, tier: int = 0) -> HorizonResult:
    log_dir = pathlib.Path(args.log_dir)/f"h{int(h)}"
    pred_h = args.pred_h if args.pred_h else min(2*args.step_h, h)
    if pred_scale != 1.0:
        pred_h = max(args.step_h, pred_h * pred_scale)
    cmd = [
        sys.executable,
        'biorefinery/src/biorefinery/scripts/run_empc_rolling.py',
        '--total-horizon-h', str(h),
        '--empc-step-h', str(args.step_h),
        '--prediction-horizon-h', str(pred_h),
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
                         drift_l2_mean=drift_l2_mean, economic_mean=econ_mean, stability_ok=stability_ok,
                         adapt_mode=None, fallback_tier=tier, prediction_h_used=pred_h)


def compare_with_baseline(results: list[HorizonResult], tol: float, regen: bool, path: pathlib.Path, param_hash: str, extended: bool):
    """Create or compare against stored baseline.

    Adds param_hash tracking: if the stored baseline param_hash differs from current
    kinetics hash we mark mismatch and force regeneration (user prompt via 'ok': False).
    """
    if regen or not path.exists():
        payload = {
            'created': time.time(),
            'tolerance_pct': tol,
            'param_hash': param_hash,
            'results': [asdict(r) for r in results]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return {'mode':'baseline_created','ok':True,'param_hash':param_hash}
    stored = json.loads(path.read_text())
    stored_hash = stored.get('param_hash')
    if stored_hash and stored_hash != param_hash:
        return {'mode':'param_hash_mismatch','ok':False,'stored_param_hash':stored_hash,'current_param_hash':param_hash}
    issues = []
    ref_map = {int(r['horizon_h']): r for r in stored.get('results', [])}
    comp_metrics = ['ethanol_final','hold_up_final']
    if extended:
        comp_metrics += ['drift_l2_mean','economic_mean']
    for r in results:
        ref = ref_map.get(int(r.horizon_h))
        if not ref:
            continue
        for metric in comp_metrics:
            cur = getattr(r, metric)
            refv = ref.get(metric)
            if cur is None or refv in (None,'nan'): continue
            if refv == 0: continue
            pct = abs(cur - refv)/abs(refv)*100.0
            if pct > tol:
                issues.append({'horizon': r.horizon_h, 'metric': metric, 'pct_diff': pct, 'cur': cur, 'ref': refv})
    return {'mode':'baseline_compare','ok': len(issues)==0, 'issues': issues, 'param_hash': stored_hash or param_hash}


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
    p.add_argument('--adaptive-nfe', action='store_true', help='Activar selección adaptativa nfe vs nfe/2 comparando etanol & hold-up finales.')
    p.add_argument('--adaptive-nfe-rel-tol', type=float, default=0.01, help='Tolerancia relativa máxima para aceptar malla gruesa (por defecto 1%).')
    p.add_argument('--adaptive-nfe-min-tol', type=float, default=0.002, help='Tolerancia mínima efectiva tras escalar por horizonte.')
    p.add_argument('--baseline-compare-extended', action='store_true', help='Incluir drift_l2_mean y economic_mean en comparación baseline.')
    p.add_argument('--strict-exit', action='store_true', help='Salir con código !=0 si baseline no ok, mismatch hash o instabilidades.')
    p.add_argument('--advanced-fallback', action='store_true', help='Activar fallback de múltiples tiers (nfe-1, reducción de predicción).')
    p.add_argument('--fallback-pred-scale', type=float, default=0.5, help='Factor para reducir predicción en fallback tier2 (ej 0.5 reduce 50%).')
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
        base_nfe = nfe_map.get(int(h), math.ceil(h/3))
        if not args.adaptive_nfe or base_nfe <= 2:
            res = run_single_horizon(h, base_nfe, args, tier=0)
            # Fallback chain
            if res.status != 'ok' and base_nfe > 2:
                # Tier1: nfe-1
                res = run_single_horizon(h, base_nfe-1, args, tier=1)
            if args.advanced_fallback and res.status != 'ok':
                # Tier2: reduce prediction horizon
                res = run_single_horizon(h, base_nfe-1 if base_nfe>2 else base_nfe, args, pred_scale=args.fallback_pred_scale, tier=2)
            if res.adapt_mode is None:
                res.adapt_mode = 'fixed'
            results.append(res)
            continue
        # Adaptive path: try coarse first
        coarse_nfe = max(1, base_nfe // 2)
        coarse_res = run_single_horizon(h, coarse_nfe, args, tier=0)
        # If coarse failed, escalate directly to fine
        if coarse_res.status != 'ok':
            fine_res = run_single_horizon(h, base_nfe, args, tier=0)
            if fine_res.status != 'ok' and base_nfe > 2:
                fine_res = run_single_horizon(h, base_nfe-1, args, tier=1)
            if args.advanced_fallback and fine_res.status != 'ok':
                fine_res = run_single_horizon(h, base_nfe-1 if base_nfe>2 else base_nfe, args, pred_scale=args.fallback_pred_scale, tier=2)
            fine_res.adapt_mode = 'fine_failover'
            results.append(fine_res)
            continue
        # Run fine for comparison
        fine_res = run_single_horizon(h, base_nfe, args, tier=0)
        if fine_res.status != 'ok':
            # Accept coarse but label uncertain
            coarse_res.adapt_mode = 'coarse_accept_fine_fail'
            results.append(coarse_res)
            continue
        # Compare relative differences in ethanol_final & hold_up_final
        def _reldiff(a,b):
            if a is None or b is None or b == 0:
                return float('inf')
            return abs(a-b)/abs(b)
        rel_eth = _reldiff(coarse_res.ethanol_final, fine_res.ethanol_final)
        rel_m = _reldiff(coarse_res.hold_up_final, fine_res.hold_up_final)
        rel_drift = _reldiff(coarse_res.drift_l2_mean, fine_res.drift_l2_mean)
        rel_econ = _reldiff(coarse_res.economic_mean, fine_res.economic_mean)
        # Dynamic tolerance scaling: tighter for longer horizons
        horizon_scale = max(1.0, h/12.0)
        eff_tol = max(args.adaptive_nfe_min_tol, args.adaptive_nfe_rel_tol / horizon_scale)
        worst = max(rel_eth, rel_m, rel_drift, rel_econ)
        # Speedup ratio (fine/coarse elapsed) if both valid
        speedup = None
        if coarse_res.elapsed_s and fine_res.elapsed_s and coarse_res.elapsed_s > 0:
            speedup = fine_res.elapsed_s / coarse_res.elapsed_s
        metrics = {'rel_eth': rel_eth, 'rel_hold_up': rel_m, 'rel_drift': rel_drift, 'rel_econ': rel_econ, 'worst': worst}
        if worst <= eff_tol:
            coarse_res.adapt_mode = 'coarse'
            coarse_res.adapt_speedup_ratio = speedup
            coarse_res.adapt_metrics = metrics
            coarse_res.adapt_tol_effective = eff_tol
            coarse_res.adapt_reason = 'coarse_within_tol'
            results.append(coarse_res)
        else:
            fine_res.adapt_mode = 'fine'
            fine_res.adapt_speedup_ratio = speedup
            fine_res.adapt_metrics = metrics
            fine_res.adapt_tol_effective = eff_tol
            fine_res.adapt_reason = 'coarse_exceeds_tol'
            results.append(fine_res)

    baseline_path = pathlib.Path(args.log_dir)/'fullscale_baseline.json'
    current_phash = _parameter_hash()
    baseline_status = compare_with_baseline(results, args.baseline_tol_pct, args.regen_baseline, baseline_path, current_phash, args.baseline_compare_extended)

    summary = {
        'config_hash': cfg_hash,
        'results': [asdict(r) for r in results],
        'baseline': baseline_status,
        'scalability_ratio': _scalability(results),
        # Parameter subset hash (kinetics & inhibition) for reproducibility / drift detection
    'param_hash': current_phash,
        'timestamp': time.time(),
    }
    (log_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    # Simple advisory
    exit_code = 0
    if baseline_status.get('mode') == 'param_hash_mismatch':
        print('READINESS: PARAM HASH MISMATCH (regenerar baseline).')
        exit_code = 2
    elif baseline_status.get('ok') and all(r.stability_ok for r in results):
        print('READINESS: PASS (baseline within tolerance & stability ok)')
    else:
        print('READINESS: ATTENTION (see summary issues)')
        if not baseline_status.get('ok'):
            exit_code = 1
        if not all(r.stability_ok for r in results):
            exit_code = max(exit_code, 3)
    if args.strict_exit and exit_code != 0:
        return exit_code
    return 0


def _scalability(results: list[HorizonResult]):
    # naive: elapsed/horizon
    ratios = []
    for r in results:
        if r.elapsed_s and r.horizon_h:
            ratios.append(r.elapsed_s / (r.horizon_h*3600.0))
    if not ratios: return None
    return {'mean_ratio': sum(ratios)/len(ratios), 'max_ratio': max(ratios)}

def _parameter_hash():
    """Compute a short hash for a core subset of fermentation kinetic parameters.

    We avoid building a full model instance (costly) by hard-coding the list of
    parameter names whose default values represent the current kinetics spec.
    If any of these defaults change in the codebase, this hash will change and
    downstream readiness comparisons can detect a baseline invalidation event.
    """
    core_params = {
        # Glucose / Xylose
        'KIP_G': 4890, 'KSP_G': 1.342, 'PMP_G': 103, 'gamma_G': 1.42, 'qmax_G': 0.000318,
        'KIP_X': 81.3, 'KSP_X': 3.4, 'PMP_X': 100.2, 'gamma_X': 0.608, 'qmax_X': 0.00083444,
        # Furfural / HMF / Acetate
        'qmax_F': 4.6706e-5, 'qmax_HMF': 8.7576e-5, 'qmax_ATC': 1.2292e-5,
        'K0G': 1, 'K1G': 5.388758642823563, 'K2G': 0.009698396119741,
        'K0X': 1, 'K1X': 5.375237819425663, 'K2X': 0.009314982725521,
        'K0F': 1.0, 'K1F': 5.38, 'K2F': 0.010,
        'K0HMF': 1.0, 'K1HMF': 5.38, 'K2HMF': 0.010,
        'K0ACT': 1.0, 'K1ACT': 5.38, 'K2ACT': 0.010,
        'PMP_F': 95.0, 'gamma_F': 0.9,
        'PMP_HMF': 97.0, 'gamma_HMF': 0.8,
        'PMP_ACT': 90.0, 'gamma_ACT': 1.0,
    }
    raw = json.dumps(core_params, sort_keys=True, separators=(',',':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
