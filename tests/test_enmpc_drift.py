import json
import subprocess
import sys
import pytest

PYTHON = sys.executable

@pytest.mark.timeout(150)
def test_enmpc_drift_metrics(tmp_path):
    out = tmp_path / 'enmcp_drift.json'
    cmd = [PYTHON, '-m', 'biorefinery.scripts.run_enmpc',
           '--total-time-h','24','--horizon-time-h','12','--step-time-h','6',
           '--nfe','3','--total-elements','24',
           '--execution-disturbance-alpha','0.05','--export-step-only','--seed','42',
           '--output', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"ENMPC drift run failed: {r.stderr}\nSTDOUT:{r.stdout}"
    data = json.loads(out.read_text())
    # Confirm metadata flags
    meta = data['meta']
    assert meta['execution_disturbance_alpha'] == 0.05
    assert meta['export_step_only'] is True
    # Check drift metrics existence and at least one non-null > 0
    l2_vals = []
    max_vals = []
    for rec in data['records']:
        # For first record drift may be None if not computed until after applying disturbance
        if rec['drift_l2'] is not None:
            l2_vals.append(rec['drift_l2'])
        if rec['drift_max_abs'] is not None:
            max_vals.append(rec['drift_max_abs'])
    assert l2_vals and any(v > 0 for v in l2_vals), 'Expected positive drift_l2 with execution disturbance'
    assert max_vals and any(v > 0 for v in max_vals), 'Expected positive drift_max_abs with execution disturbance'
