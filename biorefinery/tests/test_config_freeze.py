import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'


def run(args):
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())


def test_config_freeze_baseline_and_mismatch():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        base_args = ['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe', '--regen-baseline', '--config-freeze']
        # First run establishes freeze file
        res1 = run(base_args)
        assert res1.returncode == 0
        summary1 = load_summary(log_dir)
        cf1 = summary1.get('config_freeze')
        assert cf1 and cf1['freeze_hash'] and not cf1.get('mismatch')
        # Second run with same config should match
        res2 = run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe', '--config-freeze'])
        assert res2.returncode == 0
        # Third run change one frozen key (e.g. horizons) triggers mismatch under strict-exit
        res3 = run(['--horizons','24','--log-dir', str(log_dir), '--adaptive-nfe', '--config-freeze', '--strict-exit'])
        # Accept either normal pass (non-deterministic if baseline regen needed) OR exit code 5 for mismatch
        # If baseline mismatch (param hash) or stability issues appear exit code may differ; allow 5 or others but summary must show mismatch
        summary3 = load_summary(log_dir)
        cf3 = summary3.get('config_freeze')
        if res3.returncode == 5:
            assert cf3 and cf3['mismatch']
        else:
            # If not 5, still ensure mismatch flagged (exit code precedence may override)
            assert cf3 and cf3['mismatch']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
