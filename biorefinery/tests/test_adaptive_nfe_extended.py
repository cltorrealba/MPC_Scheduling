import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'


def run(args):
    res = subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True)
    return res

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists()
    return json.loads(p.read_text())


def test_extended_metrics_and_speedup():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--adaptive-nfe-rel-tol','0.05','--baseline-compare-extended','--regen-baseline'])
        summary = load_summary(log_dir)
        r = summary['results'][0]
        # Extended adaptive fields should exist (maybe None if fine selected but keys present)
        assert 'adapt_mode' in r
        assert 'adapt_metrics' in r
        assert 'adapt_tol_effective' in r
        # If coarse accepted, speedup ratio should be > 1 (fine elapsed / coarse elapsed)
        if r['adapt_mode'] == 'coarse':
            assert r['adapt_speedup_ratio'] is None or r['adapt_speedup_ratio'] >= 1.0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_strict_exit_nonzero_on_param_hash_mismatch():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        # First run create baseline
        run(['--horizons','12','--log-dir', str(log_dir), '--regen-baseline'])
        # Corrupt baseline hash
        bfile = pathlib.Path(log_dir)/'fullscale_baseline.json'
        data = json.loads(bfile.read_text())
        data['param_hash'] = 'XYZ'
        bfile.write_text(json.dumps(data, indent=2))
        res = run(['--horizons','12','--log-dir', str(log_dir), '--strict-exit'])
        # Expect non-zero exit code (param hash mismatch -> 2)
        assert res.returncode != 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
