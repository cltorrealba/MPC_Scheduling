# Scenario System

This directory documents the reproducible scenario system that unifies fermentation and scheduling configuration.

## Folder Layout

- `biorefinery/scenarios/schema.json` JSON Schema for validation (draft-07).
- `biorefinery/scenarios/example_basic.json` Minimal working example.

## Scenario JSON Top-Level Fields

| Field | Type | Notes |
|-------|------|-------|
| name | string | Unique identifier (used for hashing / indexing) |
| description | string | Optional human readable summary |
| version | string | Semantic-style version prefixed with `v` (e.g. `v1.0`) |
| seed | integer | RNG seed applied globally on load for deterministic sampling |
| tags | array[string] | Arbitrary labels ("demo", "benchmark", etc.) |
| fermentation | object | Sub-spec for `FermentationConfig` mapping |
| scheduling | object | Sub-spec for `SchedulingConfig` mapping |

## Fermentation Sub-Spec
Maps directly to `FermentationConfig` fields (omitting those not yet scenario-exposed). Example:
```json
{
  "horizon_h": 6.0,
  "nfe": 3,
  "include_kinetics": true,
  "detailed_kinetics": false,
  "initial_concentrations": {"G": 10.0, "X": 5.0}
}
```

## Scheduling Sub-Spec
Key arrays:
- `tasks`: each entry -> `name`, `units`, `inputs` (state fractions), `outputs`, `min_batch`, `max_batch`, `process_time_h`.
- `units`: minimal list of unit dictionaries `{ "name": "U1", "kind": "reactor" }`.
- `states`: list of state identifiers.
- `demand`: array of `{ state, t, value }` entries converted to a `(state, t)` mapping.

## Validation
If `jsonschema` is installed, structural validation is enforced when calling `load_scenario`. Without it, scenarios still load (soft dependency) to keep lightweight environments usable.

Install optional dependency:
```bash
pip install jsonschema
```

## Programmatic Use
```python
from biorefinery.models.scenario_loader import load_scenario
scn = load_scenario("biorefinery/scenarios/example_basic.json")
ferment_cfg = scn.fermentation
sched_cfg = scn.scheduling
```

## Reproducibility Notes
- The `seed` applies Python's `random.seed` at load; extend to NumPy/other RNGs in future.
- A future enhancement will compute a scenario hash (schema + ordered content) to embed into run artifacts.

## Next Enhancements
1. Scenario hash + integrity embedding in checkpoints.
2. Support overrides via CLI (e.g., `--override fermentation.horizon_h=8`).
3. Multiple demand entries per state at different times.
4. Optional stochastic parameter sampling (guarded by fixed seed).
