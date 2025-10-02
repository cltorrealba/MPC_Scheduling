import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists(), 'Missing summary.json'
    return json.loads(p.read_text())

# We cannot easily force solver failure deterministically here; this test focuses on presence of fields.

def test_fallback_fields_present():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--advanced-fallback','--fallback-pred-scale','0.6','--regen-baseline'])
        data = load_summary(log_dir)
        r = data['results'][0]
        assert 'fallback_tier' in r
        assert 'prediction_h_used' in r
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
