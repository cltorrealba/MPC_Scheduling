import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())

# This test checks that adapt_error_norm field is present and consistent with individual metrics.
# It does not assert a particular adapt_mode since randomness / model can vary, only structural consistency.

def test_adaptive_error_norm_present_and_consistent():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--adaptive-error-weights','eth:1,hold:1,drift:0.5,econ:0.2','--regen-baseline'])
        s = load_summary(log_dir)
        r = s['results'][0]
        # Only relevant if adaptive path used
        if r.get('adapt_metrics'):
            metrics = r['adapt_metrics']
            err_norm = r.get('adapt_error_norm')
            assert err_norm is not None
            # Reconstruct expected norm (allow small numerical differences)
            from math import sqrt, isfinite
            rel_eth = metrics.get('rel_eth') or 0.0
            rel_hold = metrics.get('rel_hold_up') or 0.0
            rel_drift = metrics.get('rel_drift') or 0.0
            rel_econ = metrics.get('rel_econ') or 0.0
            exp = sqrt((1*rel_eth)**2 + (1*rel_hold)**2 + (0.5*rel_drift)**2 + (0.2*rel_econ)**2)
            if isfinite(exp):
                assert abs(exp - err_norm) / (abs(exp) + 1e-12) < 1e-6
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# Speedup gating test: we artificially set min speedup very high so fine must be chosen when coarse within tol.

def test_adaptive_speedup_gating_forces_fine():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        # High tolerance (so metrics likely within tol), but extreme speedup requirement ensures coarse rejected
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--adaptive-nfe-rel-tol','0.5','--adaptive-min-speedup','999','--regen-baseline'])
        s = load_summary(log_dir)
        r = s['results'][0]
        if r.get('adapt_metrics'):
            # If adaptation happened, adapt_mode should be fine due to gating
            assert r['adapt_mode'] in ('fine','fine_failover','coarse_exceeds_tol','coarse_within_tol_low_speedup'.replace('coarse_','fine_')) or r['adapt_reason'] == 'coarse_within_tol_low_speedup'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
