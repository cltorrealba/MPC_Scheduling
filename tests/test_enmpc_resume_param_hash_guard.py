import json, subprocess, sys, pytest, tempfile, pathlib
from pathlib import Path

RUN = Path('biorefinery/src/biorefinery/scripts/run_enmpc.py')

@pytest.mark.timeout(120)
def test_resume_param_hash_guard(tmp_path):
    if not RUN.exists():
        pytest.skip('run_enmpc not found')
    base = tmp_path / 'base.json'
    # Run with param hashing enabled
    r = subprocess.run([sys.executable, str(RUN), '--total-time-h','4','--step-time-h','1','--horizon-time-h','2', '--nfe','2','--total-elements','10','--hash-params','--max-iterations','2','--output', str(base)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    data = json.loads(base.read_text())
    prev_param_hash = data['meta'].get('param_hash')
    if not prev_param_hash:
        pytest.skip('param_hash not generated')
    # Simulate param change by editing file param_hash (simulate mismatch vs current)
    mutated = json.loads(base.read_text())
    mutated['meta']['param_hash'] = 'deadbeefcafefeed'
    base.write_text(json.dumps(mutated))
    # Resume expecting failure unless ignoring param hash
    r2 = subprocess.run([sys.executable, str(RUN), '--resume-from', str(base), '--total-time-h','4','--step-time-h','1','--horizon-time-h','2','--nfe','2','--total-elements','10','--hash-params','--max-iterations','1','--output', str(tmp_path/'out.json')], capture_output=True, text=True)
    assert r2.returncode != 0, 'Expected failure due to param hash mismatch'
    assert 'Parameter hash mismatch' in (r2.stderr + r2.stdout)
    # Now override
    r3 = subprocess.run([sys.executable, str(RUN), '--resume-from', str(base), '--ignore-param-hash','--total-time-h','4','--step-time-h','1','--horizon-time-h','2','--nfe','2','--total-elements','10','--hash-params','--max-iterations','1','--output', str(tmp_path/'ok.json')], capture_output=True, text=True)
    assert r3.returncode == 0, r3.stderr
