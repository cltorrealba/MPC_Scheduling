import json
import subprocess
import sys
import pytest
from pathlib import Path

PYTHON = sys.executable

@pytest.mark.timeout(150)
def test_enmpc_resume_flow(tmp_path):
    # First partial run (limit to 1 iteration)
    part = tmp_path / 'partial.json'
    full = tmp_path / 'resumed.json'
    cmd_part = [PYTHON, '-m', 'biorefinery.scripts.run_enmpc',
                '--total-time-h','24','--horizon-time-h','12','--step-time-h','6',
                '--nfe','3','--total-elements','24','--max-iterations','1',
                '--output', str(part)]
    r1 = subprocess.run(cmd_part, capture_output=True, text=True)
    assert r1.returncode == 0, f"Partial run failed: {r1.stderr}\nSTDOUT:{r1.stdout}"
    data_part = json.loads(part.read_text())
    assert len(data_part['records']) == 1, 'Partial run should have exactly 1 iteration'
    # Resume for remaining iterations
    cmd_resume = [PYTHON, '-m', 'biorefinery.scripts.run_enmpc',
                  '--total-time-h','24','--horizon-time-h','12','--step-time-h','6',
                  '--nfe','3','--total-elements','24','--resume-from', str(part),
                  '--output', str(full)]
    r2 = subprocess.run(cmd_resume, capture_output=True, text=True)
    assert r2.returncode == 0, f"Resume run failed: {r2.stderr}\nSTDOUT:{r2.stdout}"
    data_full = json.loads(full.read_text())
    # Expect total iterations > partial
    assert len(data_full['records']) > len(data_part['records']), 'Resume did not add iterations'
    # Verify first record unchanged between partial and full
    for key in ['iteration','t_start_s','t_end_s','applied_control']:
        assert data_full['records'][0][key] == data_part['records'][0][key], 'First record mismatch after resume'
    # Check predicted/realized state presence in all records
    for rec in data_full['records']:
        assert 'predicted_end_state' in rec and 'realized_end_state' in rec
        assert 'C' in rec['predicted_end_state'] and 'M' in rec['predicted_end_state']
        assert 'C' in rec['realized_end_state'] and 'M' in rec['realized_end_state']
    # Meta resume_source should be set
    assert 'resume_source' in data_full['meta']
