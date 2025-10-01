"""Script entrypoints for the biorefinery package.

This namespace exposes runnable modules (python -m biorefinery.scripts.<module>)
including:
 - run_dsda_multistart
 - benchmark_baseline
 - run_mpc / run_enmpc prototypes

Adding this file ensures Python treats 'biorefinery.scripts' as a package so tests
invoking subprocess with -m resolution succeed.
"""

__all__ = []
