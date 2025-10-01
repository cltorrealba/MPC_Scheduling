import json, sys, subprocess, pytest
PYTHON = sys.executable

@pytest.mark.timeout(120)
def test_enmpc_meta_and_no_rates(tmp_path):
    out = tmp_path / 'enmcp_meta.json'
    cmd = [PYTHON,'-m','biorefinery.scripts.run_enmpc','--total-time-h','12','--horizon-time-h','12','--step-time-h','6',
           '--nfe','2','--total-elements','12','--execution-disturbance-alpha','0.02','--force-nonzero-drift',
           '--no-rates','--output',str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"Run failed: {r.stderr}\nSTDOUT:{r.stdout}"
    data = json.loads(out.read_text())
    meta = data['meta']
    assert 'config_hash' in meta and len(meta['config_hash']) == 16
    assert meta.get('drift_definition')
    assert meta['no_rates'] is True
    assert meta['force_nonzero_drift'] is True
    traj = data['trajectory']
    assert 'q_series' not in traj and 'R_series' not in traj, 'Rates should be omitted with --no-rates'
    # Drift metrics should exist and at least one positive
    l2_vals = [rec['drift_l2'] for rec in data['records'] if rec['drift_l2'] is not None]
    assert l2_vals and any(v > 0 for v in l2_vals)
