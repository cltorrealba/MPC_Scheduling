import json, tempfile, shutil, pathlib
import subprocess, sys

def run_readiness(tmpdir, extra_args=None):
    log_dir = tmpdir / 'logs'
    cmd = [sys.executable, 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py', '--horizons','12', '--log-dir', str(log_dir)]
    if extra_args:
        cmd += extra_args
    res = subprocess.run(cmd, capture_output=True, text=True)
    summary_path = log_dir / 'summary.json'
    assert summary_path.exists(), f"summary.json not created. stderr={res.stderr}"
    data = json.loads(summary_path.read_text())
    return data, log_dir

def test_param_hash_stored_and_matches():
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    try:
        # First run creates baseline
        data1, log_dir = run_readiness(tmpdir, ['--regen-baseline'])
        phash1 = data1['param_hash']
        baseline_file = log_dir / 'fullscale_baseline.json'
        stored = json.loads(baseline_file.read_text())
        assert stored.get('param_hash') == phash1
        # Second run (no regen) should compare with same hash and report ok
        data2, _ = run_readiness(tmpdir)
        assert data2['baseline']['ok'] is True
        assert data2['baseline'].get('mode') == 'baseline_compare'
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def test_param_hash_mismatch_detection(monkeypatch):
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    try:
        data1, log_dir = run_readiness(tmpdir, ['--regen-baseline'])
        phash1 = data1['param_hash']
        # Corrupt the stored param_hash to simulate model change
        baseline_file = log_dir / 'fullscale_baseline.json'
        stored = json.loads(baseline_file.read_text())
        stored['param_hash'] = 'DEADBEEF'
        baseline_file.write_text(json.dumps(stored, indent=2))
        # Run again - should flag mismatch
        data2, _ = run_readiness(tmpdir)
        assert data2['baseline']['mode'] == 'param_hash_mismatch'
        assert data2['baseline']['ok'] is False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
