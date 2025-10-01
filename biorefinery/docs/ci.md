# CI Strategy

Two-tier pipeline to balance fast feedback and coverage.

## Jobs
1. `fast` (Python 3.10 only)
   - Runs a curated subset of lightweight tests (API contracts, minimal scheduling, scenario loader, plotting, dsda wrapper).
   - Goal: < 1 minute feedback on PRs.
2. `extended` (Python 3.9, 3.10, 3.11)
   - Full test suite.
   - Depends on fast job succeeding.

## Selection Logic
Fast subset uses `pytest -k` expression:
```
api_contract or dsda_minimal or scheduling_minimal or scenario_loader or plot_enmpc_quick
```
Adjust by renaming or adding targeted tests to keep it lean.

## Future Enhancements
- Introduce a `@pytest.mark.slow` marker and exclude in fast job (`-m "not slow"`).
- Add benchmark regression guard consuming JSON from `benchmark_baseline.py`.
- Collect coverage in extended job and upload artifact.
- Add Windows runner for solver compatibility once stabilized.
