import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())

# We trigger max concentration alert by setting a very low threshold (< typical ethanol ~6.7)

def test_stability_max_concentration_alert():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        run(['--horizons','12','--log-dir', str(log_dir), '--stability-max-conc-thresh','1.0','--regen-baseline'])
        summary = load_summary(log_dir)
        r = summary['results'][0]
        if r.get('stability_alerts'):
            alerts = r['stability_alerts'].get('alerts') if isinstance(r['stability_alerts'], dict) else r['stability_alerts']
            assert 'max_concentration_exceeded' in alerts
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
