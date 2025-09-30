# Biorefinery Optimization Architecture

## Overview
This document summarizes the refactor from a monolithic legacy script (`biorefinery_models/Fermentation_Scheduling_and_MPC.py`) into a modular Python package under `biorefinery/src/biorefinery`. The goal is to separate pure optimization / enumeration utilities from domain model construction and experimentation logic, enabling maintainability, testing, and incremental feature evolution.

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

## Fermentation Builder Kinetics Extraction (Incremental Design)

The new `build_fermentation_model(include_kinetics: bool, detailed_kinetics: bool)` supports a progressive mode:

| Aspect | include_kinetics=False | include_kinetics=True (detailed_kinetics=False) | include_kinetics=True & detailed_kinetics=True |
|--------|------------------------|-----------------------------------------------|------------------------------------------------|
| Params | Minimal (time, capacity) | Adds yields (`Y_*`), qmax, inhibition constants (`KI_*`, `KIP_*`, `KSP_*`), pH params (`K0/1/2{G,X}`) | Same as middle column |
| Vars   | `C`, `M`, feeds, `pH` | + uptake `q[t,s]` (G,X,F,HMF,ACT) & product rates `R[t,r]` | Same |
| Constraints | Mass skeleton only | Yield-based stub: ethanol, acetate from HMF, CO2 aggregate | Adds detailed glucose & xylose uptake (Gaussian pH + multi-inhibition) |
| Future | — | Add detailed remaining substrates | Couple ODE balances & route toggles |

Rationale: keep default lightweight for unit tests / CI while enabling progressive migration without breaking legacy script functionality.

Next Kinetics Steps:
1. (Partial Done) Detailed uptake expressions for glucose & xylose (flag `detailed_kinetics`).
2. Extend to furfural, HMF, acetate with conditional activation under same flag or new granular flags.
3. Tie concentration ODEs (`dCdt`) to uptake/production terms; add initial condition mapping and consistent units review.
4. Scenario toggles / route activation flags to integrate with DSDA external variable logic (external enumeration of pathway activation).
5. Regression tests comparing selected legacy trajectories vs new builder outputs (tolerance bands) + sensitivity tests (pH, inhibitor levels).

## DSDA Readiness Enhancements (Current Status)
Implemented to enable discrete search over metabolic route availability:

- `route_config`: `Param(mutable=True)` indexed over ['G','X','F','HMF','ACT'] multiplicando las ecuaciones de velocidad detalladas (`q`). Valor 0 desactiva la ruta (tasa = 0), valor 1 la activa.
- Helper `set_route_activation(model, route, active)` encapsula la mutación para bucles de enumeración.
- Utilitario `get_route_external_variables(model)` expone snapshot 0/1 listo para integrarse a la capa de external vars del DSDA.
- `initial_concentrations`: argumento del builder fijando condiciones iniciales en `t.first()` vía `Var.fix()`, garantizando reproducibilidad entre iteraciones DSDA.
- Balances diferenciales extendidos (`G`, `X`, `Eth`, `F`, `HMF`, `ACT`) enlazan tasas a derivadas (`dCdt * final_time = +/- q/R`) permitiendo que cambios discretos en rutas afecten el objetivo dinámicamente.
 - Se añadieron balances de `Cell` (crecimiento neto simplificado) y `CO2` (producción agregada) y un flag `include_dilution` que introduce términos de dilución y alimentación basados en `F_C5liquid` y `F_liquified_fibers` y parámetros `feed_conc[j]`.
### Dilution / Feed Modeling
Cuando `include_dilution=True`:
```
 dC_j/dt * final_time = RHS_core
                        - (F_total / M) * C_j
                        + (F_total / M) * feed_conc[j]
```
con `F_total = F_C5liquid + F_liquified_fibers`.
Para especies sin entrada, `feed_conc[j]=0`.

Limitaciones actuales:
- No se modela cambio de volumen explícito distinto de M(t) base.
- No se ajustan rendimientos por mantenimiento dependiente de sustrato (simplificado).

Planned short-term extensions:
1. Incorporar balance de Biomasa y CO2 incluyendo términos de dilución / alimentación.
2. Usar `get_route_external_variables` dentro de un adaptador que alimente `external_ref`.
3. Extender test de regresión (ya existe monotonicidad simple) a combinaciones múltiples de rutas (2 o más desactivadas).

Interface sketch for external var extraction (futuro):
```python
def get_route_external_variables(model):
  return {f"route_active_{r}": int(model.route_config[r].value) for r in model.route_config}
```

Esto permitirá mapear directamente a la lógica existente de enumeración sin re-estructurar drásticamente el flujo DSDA actual.

Testing Note: Current tests assert presence/absence of components under the flag; future tests will include numeric sanity checks on rate magnitudes and monotonicity under perturbations.
