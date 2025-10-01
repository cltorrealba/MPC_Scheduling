"""Compare two benchmark JSON reports and fail on performance regression.

Usage (CLI):
  python -m biorefinery.scripts.compare_benchmark --baseline path/ref.json --new path/new.json \
      --threshold 0.10 --strict

Exit codes:
  0 -> OK (no regressions above threshold)
  1 -> Usage / file / JSON error
  2 -> Regression detected (or scenario hash mismatch in strict mode)

Definitions:
  A regression is flagged when new_mean > baseline_mean * (1 + threshold)
  Only metrics with numeric baseline_mean > 1e-12 are considered.
  Metrics auto-discovered inside each top-level section (e.g. fermentation, scheduling)
  under its "summary" mapping for entries shaped like {"mean": <number>, ...}.

Scenario hash:
  If both files contain report['scenario']['scenario_hash'] and they differ, this
  triggers a failure in strict mode. Use --allow-scenario-mismatch to ignore.

Optional:
  --warn-only converts regression detection into warnings (still returns 0).
"""
from __future__ import annotations

import argparse, json, sys, math
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class MetricDiff:
    path: str
    baseline: float
    new: float
    rel_increase: float  # (new - baseline)/baseline
    regresses: bool


def _discover_metrics(section: Dict[str, Any], section_name: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not section:
        return out
    summary = section.get("summary") if isinstance(section, dict) else None
    if not isinstance(summary, dict):
        return out
    for key, val in summary.items():
        if isinstance(val, dict) and "mean" in val and isinstance(val["mean"], (int, float)):
            out[f"{section_name}.{key}"] = float(val["mean"])  # path pattern
    return out


def compute_regressions(baseline: Dict[str, Any], new: Dict[str, Any], threshold: float) -> List[MetricDiff]:
    diffs: List[MetricDiff] = []
    # Top-level sections we care about (present or not)
    for section_name in ["fermentation", "scheduling"]:
        base_sec = baseline.get(section_name)
        new_sec = new.get(section_name)
        base_metrics = _discover_metrics(base_sec, section_name)
        new_metrics = _discover_metrics(new_sec, section_name)
        for path, base_mean in base_metrics.items():
            if path not in new_metrics:
                continue  # silently ignore missing new metric
            new_mean = new_metrics[path]
            if base_mean <= 1e-12:
                continue  # avoid divide-by-zero / meaningless ratio
            rel = (new_mean - base_mean) / base_mean
            diffs.append(MetricDiff(path=path, baseline=base_mean, new=new_mean, rel_increase=rel, regresses=rel > threshold))
    return diffs


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Comparar dos benchmarks y detectar regresiones")
    ap.add_argument("--baseline", required=True, help="Archivo benchmark de referencia")
    ap.add_argument("--new", required=True, help="Archivo benchmark nuevo a validar")
    ap.add_argument("--threshold", type=float, default=0.10, help="Umbral relativo (ej 0.10 = 10% incremento permitido)")
    ap.add_argument("--allow-scenario-mismatch", action="store_true", help="No fallar si difiere scenario_hash")
    ap.add_argument("--warn-only", action="store_true", help="No usar código de salida 2 aún con regresión")
    args = ap.parse_args(argv)

    try:
        baseline = _load_json(args.baseline)
        new = _load_json(args.new)
    except Exception as e:
        print(f"Error leyendo JSON: {e}", file=sys.stderr)
        return 1

    # Scenario hash check
    b_hash = None
    n_hash = None
    try:
        b_hash = baseline.get("scenario", {}).get("scenario_hash")
        n_hash = new.get("scenario", {}).get("scenario_hash")
    except Exception:
        pass
    scenario_mismatch = b_hash and n_hash and (b_hash != n_hash)

    diffs = compute_regressions(baseline, new, args.threshold)
    regressions = [d for d in diffs if d.regresses]

    # Report
    print("Benchmark comparison report:")
    if b_hash or n_hash:
        print(f"  scenario_hash baseline={b_hash} new={n_hash} mismatch={scenario_mismatch}")
    print(f"  Threshold: {args.threshold*100:.1f}%")
    if not diffs:
        print("  No metrics found to compare (posible formato inesperado)")
    else:
        for d in diffs:
            status = "REGRESSION" if d.regresses else "OK"
            print(f"  {d.path}: base={d.baseline:.6g} new={d.new:.6g} rel+={d.rel_increase*100:.2f}% -> {status}")

    if scenario_mismatch and not args.allow_scenario_mismatch:
        print("ERROR: scenario_hash difiere y no se permitió mismatch", file=sys.stderr)
        return 2
    if regressions:
        msg = f"{len(regressions)} metric(s) exceden el umbral"
        if args.warn_only:
            print("WARNING: " + msg)
        else:
            print("ERROR: " + msg, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
