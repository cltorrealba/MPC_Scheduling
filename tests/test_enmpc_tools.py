import json, sys, subprocess, csv
from pathlib import Path
import pytest

RUN_SCRIPT_CANDIDATES = [
    Path('biorefinery/src/biorefinery/scripts/run_enmpc.py'),
    Path('run_enmpc.py'),
]
EXPORT_SCRIPT = Path('biorefinery/src/biorefinery/scripts/export_enmpc_csv.py')
VALIDATE_SCRIPT = Path('biorefinery/src/biorefinery/scripts/validate_enmpc.py')

def _find_run():
    for p in RUN_SCRIPT_CANDIDATES:
        if p.exists():
            return p
    return None

@pytest.mark.timeout(120)
def test_export_and_validate(tmp_path):
    run_script = _find_run()
    if run_script is None or not EXPORT_SCRIPT.exists() or not VALIDATE_SCRIPT.exists():
        pytest.skip('Required scripts not found')
    run_json = tmp_path / 'tooltest.json'
    # Minimal fast run
    cmd = [
        sys.executable, str(run_script), '--total-time-h','2','--step-time-h','0.5','--horizon-time-h','1.0',
        '--nfe','2','--total-elements','4','--constant-policy','--max-iterations','2','--output', str(run_json)
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # Validate (should be OK)
    vr = subprocess.run([sys.executable, str(VALIDATE_SCRIPT), str(run_json), '--print-summary'], capture_output=True, text=True)
    assert vr.returncode == 0, vr.stderr
    assert 'iterations' in vr.stdout
    # Export CSV
    prefix = tmp_path / 'exp'
    er = subprocess.run([sys.executable, str(EXPORT_SCRIPT), str(run_json), '--prefix', str(prefix)], capture_output=True, text=True)
    assert er.returncode == 0, er.stderr
    traj_csv = Path(f"{prefix}_trajectory.csv")
    ctrl_csv = Path(f"{prefix}_controls.csv")
    assert traj_csv.exists()
    assert ctrl_csv.exists()
    # Basic CSV content checks
    with traj_csv.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    assert 'time_s' in header
    assert len(rows) > 0
    with ctrl_csv.open() as f:
        reader = csv.reader(f)
        header_c = next(reader)
        rows_c = list(reader)
    assert 'iteration' in header_c
    assert len(rows_c) > 0
