# Performance Baseline

This document captures a reproducible way to measure core build + solve costs for the fermentation and minimal scheduling models.

## Script
Implemented in `biorefinery/scripts/benchmark_baseline.py`.

## Metrics Collected
- build_time_s: wall time to build model instance.
- solve_time_s: wall time for solver (if available in environment: ipopt for fermentation, glpk for scheduling).
- nvars / ncons: simple structural size counts.
- memory_mb_before / memory_mb_after: RSS before/after (if `psutil` installed).

## Example Run
```bash
python -m biorefinery.scripts.benchmark_baseline --repeat 3 --include-scheduling --output biorefinery/results/benchmark_example.json
```

## Interpreting Output
A JSON report with `trials` (raw per run) and `summary` (mean, stdev, min, max) is produced for each domain. Use this to detect regressions in CI by comparing mean build_time_s and solve_time_s against stored baselines.

## Versioning Guidance
When model structure changes (new equations, kinetic detail):
1. Re-run benchmark.
2. Commit new JSON result under `biorefinery/results/benchmarks/` named with date + short git SHA.
3. Update thresholds in CI (future enhancement) to allow modest growth (<10%) unless justified.

## Planned Enhancements
- Automatic scenario hash + inclusion in report.
- Optional warm start vs cold start comparison.
- Tracking Pyomo model generation memory delta without psutil (fallback heuristics).
- Export CSV summary for quick plotting.
