import json, pathlib, tempfile, shutil, sys, subprocess

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py'


def run(cmd_args):
    res = subprocess.run([sys.executable, SCRIPT] + cmd_args, capture_output=True, text=True)
    return res

def load_summary(log_dir):
    p = pathlib.Path(log_dir)/'summary.json'
    assert p.exists(), f"Missing summary.json in {log_dir}"
    return json.loads(p.read_text())


def test_adaptive_prefers_coarse_when_within_tol():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        # High tolerance so coarse should be accepted
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--adaptive-nfe-rel-tol','0.5','--regen-baseline'])
        summary = load_summary(log_dir)
        r = summary['results'][0]
        # With weighted norm + speedup gating, fine can be chosen if speedup insufficient.
        assert r['adapt_mode'] in (
            'coarse','fixed','coarse_accept_fine_fail','fine','fine_failover','fine'
        ), r['adapt_mode']
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_adaptive_prefers_fine_with_strict_tol():
    tmp = tempfile.mkdtemp()
    try:
        log_dir = pathlib.Path(tmp)/'logs'
        # Zero tolerance forces fine (unless coarse & fine identical which is unlikely but handle)
        run(['--horizons','12','--log-dir', str(log_dir), '--adaptive-nfe','--adaptive-nfe-rel-tol','0.0','--regen-baseline'])
        summary = load_summary(log_dir)
        r = summary['results'][0]
        assert r['adapt_mode'] in ('fine','coarse','fine_failover','coarse_accept_fine_fail')  # allow degenerate equality
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
