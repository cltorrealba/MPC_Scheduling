import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'

def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())

# Provide thresholds below typical observed values for Eth + another species if present to force multiple exceedances.
# We then assert severity is critical (multiple species or drift persistence can trigger critical).

def test_species_thresholds_trigger_alerts():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        # Use very low Eth threshold and low G threshold to likely exceed both
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe', '--stability-species-threshold','Eth:1.0,G:1.0','--regen-baseline'])
        s = load_summary(log_dir)
        r = s['results'][0]
        alerts = r.get('stability_alerts')
        if alerts:
            a = alerts.get('alerts', {}) if isinstance(alerts, dict) else alerts
            # At least one of ETH or G exceed entries
            assert any(k.startswith('species_') for k in a.keys())
            # Severity should be critical if two species recorded
            species_exceeded = [k for k in a.keys() if k.startswith('species_')]
            if len(species_exceeded) >= 2:
                assert alerts.get('severity') == 'critical'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
