from __future__ import annotations
"""Full-scale EMPC + Scheduling readiness pipeline orchestrator.

Sequence (default):
 1. Baseline short horizons (e.g. 12,24) with --regen-baseline + config freeze.
 2. Reproducibility run (same horizons, no regen) -> KPI drift check (<1% default).
 3. Medium horizon extension (e.g. 48) -> must pass strict exit & baseline compare.
 4. Full-scale horizon (e.g. 72) if all prior gates pass.

Outputs:
  - One log directory per step under a timestamped root.
  - pipeline_summary.json & pipeline_report.md at root.

Gating Rules (stop on failure unless --force-full):
  * Non-zero exit code (strict) fails gate.
  * Repro drift: relative diff ethanol / hold-up vs previous short run > reproducibility_tol.
  * Medium horizon adds new baseline entries? (baseline already created in step 1; 48h not in baseline -> allowed).

Note: Each readiness invocation writes its own baseline inside its log dir; this keeps runs isolated.
"""

import argparse, datetime, json, pathlib, subprocess, sys, math

PYTHON = sys.executable
READINESS_SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

def _run_readiness(log_dir: pathlib.Path, horizons: list[int], regen: bool, seed: int, adaptive: bool, strict: bool, extra_args: list[str] | None = None):
    cmd = [
        PYTHON, READINESS_SCRIPT,
        '--horizons', ','.join(str(h) for h in horizons),
        '--log-dir', str(log_dir),
        '--seed', str(seed),
        '--config-freeze', '--adaptive-nfe' if adaptive else '',
        '--strict-exit' if strict else '',
    ]
    # Clean empty strings
    cmd = [c for c in cmd if c]
    if regen:
        cmd.append('--regen-baseline')
    if extra_args:
        cmd.extend(extra_args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    summary_path = log_dir/'summary.json'
    summary = None
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
        except Exception:
            summary = None
    return {
        'cmd': cmd,
        'returncode': res.returncode,
        'stdout_tail': res.stdout.splitlines()[-5:],
        'stderr_tail': res.stderr.splitlines()[-10:],
        'summary': summary,
        'log_dir': str(log_dir)
    }

def _extract_kpis(summary):
    out = {}
    for r in (summary or {}).get('results', []):
        h = int(r.get('horizon_h'))
        out[h] = {
            'ethanol_final': r.get('ethanol_final'),
            'hold_up_final': r.get('hold_up_final')
        }
    return out

def _rel_diff(a,b):
    if a in (None,'') or b in (None,'') or b == 0:
        return math.inf
    try:
        return abs(a-b)/abs(b)
    except Exception:
        return math.inf

def build_parser():
    p = argparse.ArgumentParser(description='Sequential readiness pipeline for full-scale EMPC + Scheduling.')
    p.add_argument('--root-log-dir', default='logs/pipeline', help='Root directory for pipeline runs.')
    p.add_argument('--short-horizons', default='12,24', help='Comma-separated short horizons for baseline + reproducibility.')
    p.add_argument('--medium-horizons', default='48', help='Comma-separated horizons to extend after reproducibility.')
    p.add_argument('--full-horizons', default='72', help='Comma-separated horizons for final full-scale run.')
    p.add_argument('--seed', type=int, default=123)
    p.add_argument('--adaptive-nfe', action='store_true', default=False, help='Enable adaptive NFE in readiness runs.')
    p.add_argument('--repro-tol', type=float, default=0.01, help='Relative tolerance for reproducibility (1% default).')
    p.add_argument('--force-full', action='store_true', help='Continue to full horizons even if a gate fails.')
    p.add_argument('--extra-args', type=str, default='', help='Extra args forwarded to every readiness run (space separated).')
    p.add_argument('--strict', action='store_true', default=False, help='Pass --strict-exit to readiness runs.')
    return p

def gate_repro(prev_kpis, cur_kpis, tol):
    issues = []
    for h, metrics in cur_kpis.items():
        if h not in prev_kpis:
            continue
        for k in ['ethanol_final','hold_up_final']:
            rd = _rel_diff(metrics.get(k), prev_kpis[h].get(k))
            if rd is math.inf:
                issues.append({'horizon':h,'kpi':k,'issue':'missing_or_zero'})
            elif rd > tol:
                issues.append({'horizon':h,'kpi':k,'rel_diff':rd})
    return issues

def main():
    args = build_parser().parse_args()
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    root = pathlib.Path(args.root_log_dir)/f'pipeline_{ts}'
    root.mkdir(parents=True, exist_ok=True)
    steps = []
    short = [int(x) for x in args.short_horizons.split(',') if x.strip()]
    med = [int(x) for x in args.medium_horizons.split(',') if x.strip()]
    full = [int(x) for x in args.full_horizons.split(',') if x.strip()]
    extra_common = [e for e in args.extra_args.split() if e]

    # Step 1: Baseline (regen)
    step1 = _run_readiness(root/'step1_baseline_short', short, regen=True, seed=args.seed,
                            adaptive=args.adaptive_nfe, strict=args.strict, extra_args=extra_common)
    step1['gate'] = 'baseline_short'
    steps.append(step1)
    if step1['returncode'] != 0 and not args.force_full:
        return _finalize(root, steps, 'FAIL: baseline_short')

    # Step 2: Reproducibility
    step2 = _run_readiness(root/'step2_repro_short', short, regen=False, seed=args.seed,
                            adaptive=args.adaptive_nfe, strict=args.strict, extra_args=extra_common)
    step2['gate'] = 'repro_short'
    steps.append(step2)
    repro_issues = []
    if step2['summary'] and step1['summary']:
        repro_issues = gate_repro(_extract_kpis(step1['summary']), _extract_kpis(step2['summary']), args.repro_tol)
    step2['repro_issues'] = repro_issues
    if (step2['returncode'] != 0 or repro_issues) and not args.force_full:
        return _finalize(root, steps, 'FAIL: repro_short')

    # Step 3: Medium horizons extension
    step3 = _run_readiness(root/'step3_medium', med, regen=True, seed=args.seed,
                            adaptive=args.adaptive_nfe, strict=args.strict, extra_args=extra_common)
    step3['gate'] = 'medium'
    steps.append(step3)
    if step3['returncode'] != 0 and not args.force_full:
        return _finalize(root, steps, 'FAIL: medium')

    # Step 4: Full-scale
    step4 = _run_readiness(root/'step4_full', full, regen=True, seed=args.seed,
                            adaptive=args.adaptive_nfe, strict=args.strict, extra_args=extra_common)
    step4['gate'] = 'full'
    steps.append(step4)
    status = 'PASS' if step4['returncode'] == 0 else 'FAIL: full'
    return _finalize(root, steps, status)

def _finalize(root: pathlib.Path, steps, status: str):
    pipeline_summary = {
        'status': status,
        'steps': [
            {
                'gate': s.get('gate'),
                'returncode': s['returncode'],
                'log_dir': s['log_dir'],
                'baseline_mode': (s.get('summary') or {}).get('baseline', {}).get('mode') if s.get('summary') else None,
                'exit_analysis': _exit_reason(s),
                'repro_issues': s.get('repro_issues')
            } for s in steps
        ]
    }
    (root/'pipeline_summary.json').write_text(json.dumps(pipeline_summary, indent=2))
    # Simple markdown report
    lines = [f'# Full-Scale Readiness Pipeline\n', f'Status: **{status}**\n', '## Steps\n']
    for s in pipeline_summary['steps']:
        lines.append(f"### {s['gate']}\n")
        lines.append(f"- returncode: {s['returncode']}")
        lines.append(f"- log_dir: {s['log_dir']}")
        lines.append(f"- baseline_mode: {s['baseline_mode']}")
        lines.append(f"- exit_analysis: {s['exit_analysis']}")
        if s.get('repro_issues'):
            lines.append(f"- repro_issues: {json.dumps(s['repro_issues'], indent=2)}")
        lines.append('')
    (root/'pipeline_report.md').write_text('\n'.join(lines))
    print(json.dumps(pipeline_summary, indent=2))
    # Return non-zero if final status starts with FAIL
    if status.startswith('FAIL'):
        return 1
    return 0

def _exit_reason(step):
    rc = step['returncode']
    if rc == 0: return 'ok'
    mapping = {1:'baseline_deviation',2:'param_hash_mismatch',3:'stability_alerts',4:'fallback_tier2_used',5:'config_freeze_mismatch'}
    return mapping.get(rc, f'code_{rc}')

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
