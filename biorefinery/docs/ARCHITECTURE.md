# Biorefinery Optimization Architecture

## Overview
This document summarizes the refactor from a monolithic legacy script (`biorefinery_models/Fermentation_Scheduling_and_MPC.py`) into a modular Python package under `biorefinery/src/biorefinery`. The goal is to separate pure optimization / enumeration utilities from domain model construction and experimentation logic, enabling maintainability, testing, and incremental feature evolution.

```mermaid
flowchart LR
  subgraph Models
    F[fermentation builder]\nroute_config
    S[scheduling models]
    SCN[scenario_loader]
  end
  subgraph Optimization
    N[neighborhoods]
    EV[evaluation]
    SLV[solvers]
    ADP[dsda_adapter]
  end
  subgraph Scripts
    RDR[run_fullscale_readiness]
    PIPE[run_fullscale_pipeline]
    ENMPC[run_enmpc]
    BASE[generate_unified_baseline]
  end
  subgraph Metrics
    ECON[economic_*]
    DRIFT[drift metrics]
  end
  SCN --> F
  F --> ENMPC
  F --> RDR
  F --> ADP
  ADP --> SLV
  N --> EV --> SLV
  SLV --> RDR
  SLV --> ENMPC
  ECON --> RDR
  DRIFT --> RDR
  RDR --> PIPE
  BASE --> RDR
  ECON --> ENMPC
  DRIFT --> ENMPC
```

## Legacy Situation (Before)
- Single giant script mixing:
  - Pyomo model construction (fermentation, scheduling, MPC pieces)
  - GDP → MIP (planned) and external variable logic
  - Neighborhood generation & discrete search (D-SDA)
  - Solver configuration and direct solve loops
  - Ad‑hoc serialization (JSON initializations) and plotting
  - Hardcoded CSV path references
- Code duplication around neighborhood search, repeated patterns of: build → fix external vars → solve → evaluate neighbors.

## Current Modular Layout
```
biorefinery/
  src/biorefinery/
    models/
      data_access.py         # get_data_path() helper for CSV resolution
    optimization/
      external_ref.py        # External variable logic, dummy logic generators
      solvers.py             # Preprocess & solve subproblems with fallback
      neighborhoods.py       # Neighborhood enumerators & filtering
      evaluation.py          # Neighbor evaluation + line search orchestration
      initialization.py      # Wrapper around legacy serializer (load/dump)
    plotting/ (future)       # Centralized plotting utilities (not populated yet)
  scripts/
    run_mpc.py               # Wrapper to execute legacy script
    smoke_test.py            # Minimal artificial model and DSDA smoke test
  docs/
    ARCHITECTURE.md          # This document
  experiments/
    scenarios/build_index.py # Index of JSON initializations
  data/                      # (Planned) canonical raw/processed data storage
```

## Extracted Components
| Concern | Old Location | New Module | Notes |
|---------|-------------|------------|-------|
| External Boolean logic & reformulation stubs | Legacy functions | `optimization/external_ref.py` | Includes `dummy_logic`, `dummy_logic_v2`, `external_ref`, `get_external_information` |
| Subproblem solver orchestration | Inline loops | `optimization/solvers.py` | Adds fallback chain: GAMS+solver → direct solver → ipopt (continuous only) |
| Neighborhood generation | Multiple inline funcs | `optimization/neighborhoods.py` | Pure stateless functions returning direction dictionaries |
| Neighbor evaluation & line search (DSDA inner loops) | Mixed inside D-SDA | `optimization/evaluation.py` | Provides `evaluate_neighbors` & `do_line_search` |
| DSDA enumeration wrapper | Fragmented block | Still in legacy script as `dsda_enumeration` | Could be moved later once dependencies pruned |
| Initialization (JSON) | `model_serializer` usage scattered | `optimization/initialization.py` | Thin facade around legacy serializer preserving compatibility |
| Data path resolution | Hardcoded relative strings | `models/data_access.py` | Future centralization (CSV use still minimal) |
| Fermentation model (skeleton) | Inline giant block | `models/fermentation.py` | Incremental builder `build_fermentation_model` (partial DAE & sets) |

## DSDA Flow (Refactored)
1. Model factory builds a fresh Pyomo instance.
2. `get_external_information` collects external variable metadata.
3. `external_ref` applies fixing/reformulation logic for a trial point.
4. `solve_subproblem` performs a (NLP/MINLP/MIP) solve with graceful fallback.
5. `evaluate_neighbors` loops candidate points selecting an improving neighbor.
6. `do_line_search` extends movement along the improving direction.
7. `dsda_enumeration` (legacy wrapper) orchestrates outer neighbor search cycles.

## Solver Fallback Strategy
Order of attempts inside `solve_subproblem`:
1. GAMS interface with requested solver (e.g. `conopt4`).
2. Direct Pyomo factory for the same solver name (if installed standalone).
3. Ipopt as continuous fallback if no discrete variables.
4. Mark model status `Solver_Not_Available` otherwise.

Rationale: Keep legacy expectation of GAMS while enabling development environments without full licensed stack.

## Pending / Next Refactors
| Item | Plan |
|------|------|
| Move `dsda_enumeration` to `optimization` | After ensuring no circular imports (needs only evaluation, neighborhoods, external_ref, solvers, initialization). |
| Consolidate initialization pipelines | Unify into a domain service (load best / warm-start) with caching. |
| External GDP→MIP transformation (`extvars_gdp_to_mip`) | Implement minimal transformation OR conditionally bypass until needed. |
| Progressive migration of fermentation DAE | Move parameter blocks & constraints piecewise into builder; add regression tests per batch. |
| Plotting centralization | Extract repeated plotting code blocks into `plotting` utilities with consistent styling. |
| Test suite | Pytest-based: unit tests for each neighborhood function, evaluation logic with mocked solver, smoke test for dsda_enumeration. |
| Data ingestion | Move CSV assets from legacy folder to `data/raw` and adapt calls to `get_data_path()`. |
| Configuration | Add a lightweight settings module / dataclass (e.g., solver names, time limits). |

## Design Principles Applied
- Single Responsibility: Each module houses one axis of behavior (solver handling, neighborhood construction, evaluation logic).
- Side-Effect Containment: External file I/O isolated (initializations, data access) for easier mocking.
- Progressive Extraction: Left `dsda_enumeration` in legacy temporarily to reduce surface change while stabilizing.
- Backwards Compatibility: Kept JSON serializer interface unchanged; wrappers defer to legacy serializer.
- Fail-Safe Solver Path: Graceful degradation avoids brittle hard dependency on licensed solvers during development.
 - Centralized Configuration: Runtime tunables (solver names, time limit, logging level) sourced from environment via `biorefinery.config` dataclass.

## Migration Roadmap (High-Level)
Phase 1 (Done): Skeleton package + extraction of core optimization utilities.
Phase 2 (Done): Stabilize DSDA orchestration, add architecture & smoke test, solver fallback, configuration layer & logging centralization.
Phase 3: Move remaining orchestration (dsda_enumeration) and prune obsolete code paths from legacy script.
Phase 4: Introduce automated tests + CI (GitHub Actions) for style & functional smoke.
Phase 5: Document advanced usage, scenario configuration, and reproducibility guidelines.

## Testing Strategy (Planned)
| Layer | Test Type | Example |
|-------|-----------|---------|
| Neighborhoods | Deterministic unit | Size & symmetry of k=2 neighborhood |
| Evaluation | Mock solver injection | Ensure improvement logic selects expected neighbor |
| Line Search | Boundary tests | Stops at bounds; improvement threshold respected |
| Solver Fallback | Monkeypatch availability | Verify ipopt fallback path triggers |
| Integration | Smoke (already present) | DSDA run on tiny model returns route length ≥1 |

## Known Technical Debt
- `extvars_gdp_to_mip` still stubbed (currently a pure passthrough returning `(model, {})`). It exists only to decouple enumeration from a future generalized disjunctive programming (GDP) → MIP or NLP reformulation. When/if actual transformation logic is required, replace the stub with a function that:
  1. Inspects external (Boolean / categorical) variable structures,
  2. Applies Pyomo GDP transformations (e.g. `gdp.bigm`, `gdp.hull`) or custom linearization,
  3. Returns a mapping of original external var names (or Disjunct/Disjunction identifiers) to their transformed counterparts for traceability.
  Until then, higher-level code should not rely on the mapping being non-empty.
 - Configuration currently read once (singleton); hot-reloading requires `get_config(force_reload=True)`.
- Mixed naming conventions remain in legacy script.
- Some global variable expectations (e.g., solver names) hardcoded.
- No logging configuration centralization (print statements still present).
 - Legacy fermentation kinetics not fully migrated (now partially: parameters + stub rates with `include_kinetics`).

## How to Extend
- Add a new neighborhood: implement pure function in `neighborhoods.py`, return dict indexed from 1, import where needed.
- Plug alternative solver: extend fallback list or add configuration module.
- Support scenario sets: create YAML/JSON scenario definitions consumed by a new `experiments` runner script.

## Glossary
- DSDA: Discrete Steepest Descent Algorithm (enumerates discrete neighbor directions and performs local improvement with line search heuristic).
- External Variables: Binary/logical variables reformulated or fixed during enumeration to define subproblems.
- Initialization JSON: Serialized variable values to warm-start subsequent solves.

## Immediate Next Tasks
1. Implement minimal `extvars_gdp_to_mip` passthrough or conditional guard.
2. Move `dsda_enumeration` fully out of legacy script.
3. Add first pytest module (`tests/test_neighborhoods.py`).

---
Maintained by: Biorefinery refactor effort. Update this document when moving DSDA orchestration or adding solver configuration abstraction.

## Fermentation Builder & DSDA (Resumen)
Los detalles exhaustivos de cinéticas incrementales, rutas discretas y futuras extensiones fueron movidos a:
- `FUNCTION_REFERENCE.md` (sección Models & Optimization)
- `USAGE_GUIDE.md` (pasos prácticos para descenso local de rutas y extensión cinética)

Puntos clave conservados:
- Builder escalable mediante flags `include_kinetics`, `detailed_kinetics`, `include_dilution`.
- Rutas discretas gestionadas con `route_config` y helpers (`set_route_activation`, `optimize_routes_local_descent`).
- DSDA completo aún parcialmente desacoplado; adaptadores ligeros proporcionan experimentar sin dependencias externas pesadas.

## Readiness & Pipeline Architecture (Added Post Phase 2)

## Readiness & Pipeline Architecture (Added Post Phase 2)
Para asegurar reproducibilidad y estabilidad antes de corridas full-scale se introdujo una capa de "readiness" y un pipeline secuencial:

### Scripts Clave
- `run_fullscale_readiness.py`: Ejecuta uno o varios horizontes y produce `summary.json` con:
  - Comparación contra baseline (`fullscale_baseline.json`).
  - Adaptación NFE (malla coarse vs fine) usando norma ponderada y speedup mínimo.
  - Fallback multinivel (tier1 nfe-1, tier2 reducción horizonte predicción).
  - Alertas de estabilidad: concentraciones finales (`final_<sp>_pred`), thresholds por especie, tendencia y persistencia de deriva (`drift_l2`).
  - Congelación de configuración (`config_freeze.json`) para hash de flags críticos.
- `run_fullscale_pipeline.py`: Orquesta gates secuenciales (baseline corta → reproducibilidad → medium → full) generando `pipeline_summary.json` y reporte Markdown.

### Adaptación NFE
1. Corre malla coarse (nfe/2) y malla fine (nfe base).
2. Calcula métricas relativas (EtOH, hold-up, drift, económica) + norma ponderada con pesos configurables.
3. Acepta coarse si: (a) errores <= tolerancia efectiva y (b) speedup >= mínimo requerido.
4. Si (a) sí y (b) no -> fuerza fine (razón registrada) para evitar regresión de simulación sin ganancia significativa de tiempo.

### Fallback
Activado con `--advanced-fallback`:
- Tier0: setup original.
- Tier1: reintenta con `nfe-1`.
- Tier2: escala horizonte de predicción (`--fallback-pred-scale`).
Se registra el nivel usado para análisis; bajo modo estricto exit code 4 si solo tier2 fue necesario.

### Estabilidad
Genera objeto `stability_alerts` con entradas:
- `max_concentration_exceeded` (proxy global).
- `species_<Sp>_exceeded` por cada umbral individual.
- `drift_trend` (pendiente > threshold) y `drift_persist` (persistencia LS multi-ventana).
La severidad: `warning` (evento aislado) o `critical` (persistencia/múltiples excedencias). Afecta exit code (≥3).

### Exit Codes
Orden de prioridad (mayor domina):
0 OK, 1 desvío baseline, 2 `param_hash` mismatch, 3 estabilidad, 4 fallback tier2, 5 config freeze mismatch.

### Integración CI / Futuro
- Fast CI podría ejecutar readiness en horizontes cortos con `--strict-exit` y fallar si code≥1 salvo regeneración autorizada.
- Extended CI puede incluir coarse/fine timing para detectar degradaciones de performance.

### Justificación Arquitectónica
Separar readiness de pipeline permite reusar la misma evaluación para:
- Regresión de performance (coarse vs fine).
- Asegurar reproducibilidad (baseline + config freeze).
- Gate de estabilidad antes de horizontes largos costosos.

El diseño mantiene scripts independientes sin acoplar fuertemente al builder; se basa en entradas CLI y JSONs para permitir experimentación rápida sin modificar núcleo del modelo.
