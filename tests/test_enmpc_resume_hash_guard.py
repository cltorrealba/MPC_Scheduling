import json, subprocess, sys, pytest
from pathlib import Path
PYTHON = sys.executable

@pytest.mark.timeout(120)
def test_enmpc_resume_hash_guard(tmp_path):
    base = tmp_path / 'base.json'
    # Run with certain settings
    cmd1 = [PYTHON,'-m','biorefinery.scripts.run_enmpc','--total-time-h','12','--horizon-time-h','12','--step-time-h','6',
            '--nfe','2','--total-elements','12','--max-iterations','1','--output',str(base)]
    r1 = subprocess.run(cmd1, capture_output=True, text=True)
    assert r1.returncode == 0, f"Initial run failed: {r1.stderr}\nSTDOUT:{r1.stdout}"
    base_data = json.loads(base.read_text())
    assert 'config_hash' in base_data['meta']

    # Attempt resume changing a parameter affecting hash (add --no-rates)
    cmd_bad = [PYTHON,'-m','biorefinery.scripts.run_enmpc','--total-time-h','12','--horizon-time-h','12','--step-time-h','6',
               '--nfe','2','--total-elements','12','--no-rates','--resume-from',str(base),'--output',str(tmp_path/'resume_bad.json')]
    r_bad = subprocess.run(cmd_bad, capture_output=True, text=True)
    assert r_bad.returncode != 0, 'Resume should have failed due to hash mismatch'
    assert 'hash mismatch' in r_bad.stderr.lower()

    # Resume with override
    cmd_ok = [PYTHON,'-m','biorefinery.scripts.run_enmpc','--total-time-h','12','--horizon-time-h','12','--step-time-h','6',
              '--nfe','2','--total-elements','12','--no-rates','--ignore-config-hash','--resume-from',str(base),'--output',str(tmp_path/'resume_ok.json')]
    r_ok = subprocess.run(cmd_ok, capture_output=True, text=True)
    assert r_ok.returncode == 0, f"Override resume failed: {r_ok.stderr}\nSTDOUT:{r_ok.stdout}"
    ok_data = json.loads((tmp_path/'resume_ok.json').read_text())
    assert len(ok_data['records']) > len(base_data['records'])
