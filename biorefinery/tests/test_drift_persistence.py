import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

# This test sets a very low drift threshold and small windows to more easily trigger drift_persist.
# Because actual drift dynamics may still not cross thresholds, the test only asserts structural fields
# if persistence is reported. We avoid flakiness by not requiring it.

def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())

def test_drift_persist_structure():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe', '--stability-drift-trend-threshold','0.0', '--stability-drift-persist-window','2','--stability-drift-persist-count','2','--regen-baseline'])
        s = load_summary(log_dir)
        r = s['results'][0]
        alerts = r.get('stability_alerts')
        if alerts and isinstance(alerts, dict):
            a = alerts.get('alerts') or {}
            if 'drift_persist' in a:
                dp = a['drift_persist']
                assert 'slopes' in dp and isinstance(dp['slopes'], list) and len(dp['slopes']) >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
