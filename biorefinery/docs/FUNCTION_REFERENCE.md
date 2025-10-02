# Function & Module Reference

Concise dictionary of key public-facing functions, classes and scripts. Internal helpers (`_prefix`) are omitted.

## Models
- `build_fermentation_model(**kwargs)` (models/fermentation.py): Build incremental DAE fermentation model. Key kwargs: `include_kinetics`, `detailed_kinetics`, `initial_concentrations`, `include_dilution`, `enable_mass_balance`, `max_concentration`, `min_hold_up`.
- `set_route_activation(model, route, active)` / `set_routes_activation(model, mapping)` (fermentation.py): Toggle kinetic uptake routes (discrete switches for local search / DSDA).
- `get_route_external_variables(model)` (fermentation.py): Snapshot dict `{route_active_<R>: 0/1}` for external enumeration.
- `optimize_routes_local_descent(model, evaluator, max_iters=20)` (fermentation.py): One-flip steepest descent on routes using user evaluator.
- `load_scenario(path)` (models/scenario_loader.py): Load JSON scenario (structure: fermentation + scheduling sub-specs). Returns dataclass wrapper.
- `get_data_path(name)` (models/data_access.py): Resolve CSV file path (prefers migrated data, fallback legacy folder).
- `diagnose_model(model, max_items=20)` (models/model_diagnostics.py): Return ranked constraint residuals pre/post solve for debugging.

## Optimization / DSDA
- `solve_subproblem(model, subproblem_solver, **opts)` (optimization/solvers.py): Attempt GAMS + solver, fallback direct solver, fallback Ipopt if continuous.
- `pick_available_solver(candidates=None, return_options=False)` (solvers.py): Iterate candidate list, return first available solver (+options if requested).
- Neighborhood generators (neighborhoods.py): `neighborhood_k_eq_1..5`, `neighborhood_k_eq_inf`, `neighborhood_k_eq_l_natural`, filtering via `find_actual_neighbors`.
- DSDA adapter (dsda_adapter.py): `run_local_descent`, `steepest_improvement_step`, `one_flip_neighbors`, `evaluate_vector`, `extract_route_vector`, `apply_route_vector`. Lightweight enumeration over route vectors.
- Minimal DSDA (dsda_minimal.py) & full variant (dsda.py): Core enumeration logic (legacy-connected; see architecture doc for migration notes).
- `external_ref(...)` (external_ref.py): Apply external variable fixing/reformulation (stub/partial extraction from legacy).
- `evaluate_neighbors(...)`, `do_line_search(...)` (evaluation.py): Evaluate candidate discrete moves + extend improvement direction.

## Metrics
- `economic_aggregate` / `economic_extended` (metrics/): Functions computing economic KPIs from EMPC runs (import-level side; refer to code for symbol list).
- `metrics.py`: Shared metric utilities (drift, aggregated statistics) used by readiness & rolling EMPC.

## Reporting
- `kpi_report.generate_report(run_json_paths, output)` (reporting/kpi_report.py): Aggregate multiple run JSONs into a single KPI summary.

## Integration
- `SchedulingControlInterface` (integration/scheduling_control_interface.py): Glue between scheduling and control layers (class – narrow facade).

## Configuration & Logging
- `get_config(force_reload=False)` (config.py): Load environment-driven configuration dataclass (solver names, time limit, verbosity).
- `set_level(level)` (logging_config.py): Adjust logging verbosity at runtime.

## Legacy Compatibility
- `compute_param_hash(params)` (legacy/param_hash.py): Deterministic hash over kinetic parameter subset.
- `BaselineManager` (legacy/baseline_manager.py): Load/validate baseline artifacts (param hash match, tolerance check).
- `tolerances.py`: Central tolerance constants used in legacy validation.

## Readiness & Pipeline Scripts (scripts/)
Scripts are invoked via `python -m biorefinery.scripts.<name>` or direct path. Key ones:
- `run_fullscale_readiness.py`: Multi-horizon evaluation with adaptive NFE, stability alerts, fallback tiers, config freeze. Outputs `summary.json`.
- `run_fullscale_pipeline.py`: Sequential gates (baseline_short → repro_short → medium → full). Outputs `pipeline_summary.json`.
- `run_enmpc.py`: ENMPC loop with optional feasibility prepass and mass balance slack.
- `run_empc_rolling.py`: Rolling horizon EMPC producing CSV metrics per step.
- `generate_unified_baseline.py`: Deterministic or solved baseline with `param_hash`.
- `benchmark_baseline.py`: Build/solve timing & size metrics (`benchmark_example.json`).
- `plot_enmpc_quick.py`, `plot_enmpc_overlay.py`, `plot_empc_results.py`: Visualization utilities.
- `snapshot_results.py` / `clean_outputs.py`: Artifact packaging and cleanup.
- `compare_benchmark.py`, `run_multi_horizon_comparison.py`: Comparative analyses (performance & horizon effects).
- `integrate_scheduling_enmpc.py`, `run_integrated.py`, `run_integrated_iterative.py`: Coupled scheduling-control experimentation variants.

## Exit Codes (Readiness)
0 OK | 1 baseline deviation | 2 param hash mismatch | 3 stability alerts | 4 fallback tier2 used | 5 config freeze mismatch.

## Usage Hints
- Prefer builders + adapters (fermentation + dsda_adapter) for lightweight tests instead of legacy scripts.
- When adding new kinetic params: update `compute_param_hash` to maintain reproducibility.
- New external variable types: extend `external_ref` and route extraction helpers consistently.
- Scenario hashing (planned): once `scenario_hash` is implemented it must be embedded in baseline/readiness summaries for traceability; ensure loader produces stable ordering.

---
Actualiza este diccionario al introducir APIs públicas nuevas o renombrar funciones.
