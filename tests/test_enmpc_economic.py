import json
import subprocess
import sys
import pytest

PYTHON = sys.executable

@pytest.mark.timeout(150)
def test_enmpc_economic_with_rates(tmp_path):
    out = tmp_path / 'enmcp_econ.json'
    cmd = [PYTHON, '-m', 'biorefinery.scripts.run_enmpc',
           '--total-time-h','24','--horizon-time-h','12','--step-time-h','6',
           '--nfe','3','--total-elements','24','--economic-objective','--output', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"ENMPC economic run failed: {r.stderr}\nSTDOUT:{r.stdout}"
    data = json.loads(out.read_text())
    # Basic keys
    assert 'meta' in data and data['meta'].get('economic_objective') is True
    # Param hash (optional flag --hash-params not used here, so presence is advisory)
    if 'param_hash' in data.get('meta', {}):
        ph = data['meta']['param_hash']
        if ph is not None:
            assert isinstance(ph, str) and len(ph) >= 8
    assert 'trajectory' in data
    traj = data['trajectory']
    # q/R presence (since include_kinetics True in runner build)
    assert 'q_series' in traj and 'R_series' in traj, 'Kinetic rate series missing'
    # Non-empty series lengths align with time
    tlen = len(traj['time_s'])
    for sp, series in traj['q_series'].items():
        assert len(series) == tlen, f"q_series length mismatch for {sp}"
    for rx, series in traj['R_series'].items():
        assert len(series) == tlen, f"R_series length mismatch for {rx}"
    # Economic metric present in each record and finite
    for rec in data['records']:
        em = rec.get('economic_metric')
        assert em is not None and em == em, 'Invalid economic metric'
        assert isinstance(rec.get('ethanol_non_monotonic'), (bool, type(True)))
        assert isinstance(rec.get('neg_species'), list)
