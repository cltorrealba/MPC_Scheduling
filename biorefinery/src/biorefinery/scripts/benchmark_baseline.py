from __future__ import annotations
"""Baseline performance benchmark.
(See docs/perf.md for details.)
"""
import argparse, json, time, statistics, sys, os
from typing import Any, Dict, List

try:
    import psutil  # type: ignore
except ImportError:  # fallback
    psutil = None  # type: ignore

import pyomo.environ as pe

from biorefinery.models import (
    FermentationConfig, build_fermentation_model_v2,
    SchedulingConfig, TaskDef, UnitDef, build_minimal_scheduling_model
)

def _measure_memory_mb() -> float | None:
    if psutil is None:
        return None
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def run_fermentation_trial(cfg: FermentationConfig) -> Dict[str, Any]:
    t0 = time.perf_counter()
    build = build_fermentation_model_v2(cfg)
    build_time = time.perf_counter() - t0
    m = build.model
    solver = pe.SolverFactory("ipopt")
    solve_time = None
    term = None
    if solver.available(False):
        t1 = time.perf_counter()
        res = solver.solve(m, tee=False)
        solve_time = time.perf_counter() - t1
        term = str(res.solver.termination_condition)
    return {
        "build_time_s": build_time,
        "solve_time_s": solve_time,
        "termination": term,
        "nvars": sum(1 for _ in m.component_data_objects(pe.Var)),
        "ncons": sum(1 for _ in m.component_data_objects(pe.Constraint)),
        "param_hash": build.param_hash,
    }


def build_default_scheduling() -> SchedulingConfig:
    tasks = [
        TaskDef("T1", inputs={"A":1.0}, outputs={"B":1.0}, units=["U1"], min_batch=5, max_batch=10, process_time_h=1.0),
        TaskDef("T2", inputs={"B":1.0}, outputs={"C":1.0}, units=["U1"], min_batch=5, max_batch=10, process_time_h=1.0),
    ]
    units = [UnitDef("U1")]
    return SchedulingConfig(
        horizon_h=6.0,
        n_periods=6,
        tasks=tasks,
        units=units,
        states=["A","B","C"],
        initial_inventory={"A": 50.0},
        storage_capacity={"A":1000,"B":1000,"C":1000},
        demand={("C",5):10.0},
    )


def run_scheduling_trial(cfg: SchedulingConfig) -> Dict[str, Any]:
    t0 = time.perf_counter()
    build = build_minimal_scheduling_model(cfg)
    build_time = time.perf_counter() - t0
    m = build.model
    solver = pe.SolverFactory("glpk")
    solve_time = None
    term = None
    if solver.available(False):
        t1 = time.perf_counter()
        res = solver.solve(m, tee=False)
        solve_time = time.perf_counter() - t1
        term = str(res.solver.termination_condition)
    return {
        "build_time_s": build_time,
        "solve_time_s": solve_time,
        "termination": term,
        "nvars": sum(1 for _ in m.component_data_objects(pe.Var)),
        "ncons": sum(1 for _ in m.component_data_objects(pe.Constraint)),
    }


def aggregate_trials(trials: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trials:
        return {}
    agg: Dict[str, Any] = {}
    for key in trials[0].keys():
        nums = [t[key] for t in trials if isinstance(t[key], (int, float)) and t[key] is not None]
        if nums:
            agg[key] = {
                "mean": statistics.mean(nums),
                "stdev": statistics.pstdev(nums) if len(nums) > 1 else 0.0,
                "min": min(nums),
                "max": max(nums),
            }
        else:
            agg[key] = trials[0][key]
    return agg


def main(argv: List[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--include-scheduling", action="store_true")
    ap.add_argument("--output", type=str)
    ap.add_argument("--horizon-h", type=float, default=6.0)
    ap.add_argument("--nfe", type=int, default=3)
    args = ap.parse_args(argv)

    mem_before = _measure_memory_mb()

    ferm_cfg = FermentationConfig(horizon_h=args.horizon_h, nfe=args.nfe, detailed_kinetics=False)
    ferm_trials = [run_fermentation_trial(ferm_cfg) for _ in range(args.repeat)]
    ferm_summary = aggregate_trials(ferm_trials)

    sched_summary = None
    sched_trials: List[Dict[str, Any]] = []
    if args.include_scheduling:
        sched_cfg = build_default_scheduling()
        sched_trials = [run_scheduling_trial(sched_cfg) for _ in range(args.repeat)]
        sched_summary = aggregate_trials(sched_trials)

    mem_after = _measure_memory_mb()

    report = {
        "fermentation": {"trials": ferm_trials, "summary": ferm_summary},
        "scheduling": {"trials": sched_trials, "summary": sched_summary} if args.include_scheduling else None,
        "repeat": args.repeat,
        "memory_mb_before": mem_before,
        "memory_mb_after": mem_after,
        "environment": {"python": sys.version, "platform": sys.platform},
    }

    out_json = json.dumps(report, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_json)
    print(out_json)

if __name__ == "__main__":  # pragma: no cover
    main()
