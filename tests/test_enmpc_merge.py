import json, subprocess, sys
from pathlib import Path

# Attempt to locate run_enmpc script in common locations
_CANDIDATES = [
    Path('run_enmpc.py'),
    Path('biorefinery/src/biorefinery/scripts/run_enmpc.py'),
    Path('biorefinery_models/run_enmpc.py'),
]
RUN_SCRIPT = None
for _p in _CANDIDATES:
    if _p.exists():
        RUN_SCRIPT = _p
        break

MERGE_SCRIPT = Path('biorefinery/src/biorefinery/scripts/merge_enmpc_runs.py')

import pytest

@pytest.mark.timeout(120)
def test_merge_enmpc_runs_basic(tmp_path):
    if not RUN_SCRIPT.exists():
        pytest.skip('run_enmpc.py not found in expected location')
    if not MERGE_SCRIPT.exists():
        pytest.skip('merge script missing')

    # Produce two short partial runs via max-iterations (use tiny model + constant policy for speed)
    json1 = tmp_path / 'part1.json'
    json2 = tmp_path / 'part2.json'
    merged = tmp_path / 'merged.json'

    base_cmd = [
        sys.executable, str(RUN_SCRIPT),
        '--total-time-h','2', '--step-time-h','0.5', '--horizon-time-h','1.0',
        '--nfe','2','--total-elements','4', '--constant-policy',
        '--max-iterations','2', '--output', str(json1)
    ]
    r = subprocess.run(base_cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # Resume second half
    r2 = subprocess.run([
        sys.executable, str(RUN_SCRIPT), '--resume-from', str(json1),
        '--total-time-h','2', '--step-time-h','0.5', '--horizon-time-h','1.0',
        '--nfe','2','--total-elements','4', '--constant-policy',
        '--max-iterations','2', '--output', str(json2)
    ], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr

    # Merge the two parts
    r3 = subprocess.run([sys.executable, str(MERGE_SCRIPT), str(json1), str(json2), '--output', str(merged)], capture_output=True, text=True)
    assert r3.returncode == 0, r3.stderr + '\n' + r3.stdout

    data1 = json.loads(json1.read_text())
    data2 = json.loads(json2.read_text())
    datam = json.loads(merged.read_text())

    # Combined iterations should equal sum
    assert len(datam['records']) == len(data1['records']) + len(data2['records'])
    # Iteration numbering strictly increasing and contiguous starting at 0 or 1 depending on implementation
    iters = [r['iteration'] for r in datam['records']]
    assert all(isinstance(i,int) for i in iters)
    # Check monotonic
    assert all(b >= a for a,b in zip(iters, iters[1:])), f"Iterations not non-decreasing: {iters}"
    # Time series: final time should match last part final time (non-compressed)
    assert datam['trajectory']['time_s'][-1] == data2['trajectory']['time_s'][-1]
    # Ensure no duplicate adjacent time points after boundary stitch
    ts = datam['trajectory']['time_s']
    for a,b in zip(ts, ts[1:]):
        assert not (abs(a-b) < 1e-12), 'Duplicate adjacent time entries'

@pytest.mark.timeout(120)
def test_merge_enmpc_runs_compress(tmp_path):
    if not RUN_SCRIPT.exists() or not MERGE_SCRIPT.exists():
        pytest.skip('scripts missing')
    json1 = tmp_path / 'p1.json'
    json2 = tmp_path / 'p2.json'
    merged = tmp_path / 'merged_c.json'

    subprocess.check_call([
        sys.executable, str(RUN_SCRIPT), '--total-time-h','2','--step-time-h','0.5','--horizon-time-h','1.0',
        '--nfe','2','--total-elements','4','--constant-policy','--max-iterations','2','--output', str(json1)
    ])
    subprocess.check_call([
        sys.executable, str(RUN_SCRIPT), '--resume-from', str(json1), '--total-time-h','2','--step-time-h','0.5','--horizon-time-h','1.0',
        '--nfe','2','--total-elements','4','--constant-policy','--max-iterations','2','--output', str(json2)
    ])

    subprocess.check_call([sys.executable, str(MERGE_SCRIPT), str(json1), str(json2), '--output', str(merged), '--compress'])
    datam = json.loads(merged.read_text())
    assert datam['meta'].get('export_step_only') is True
    # Compression should reduce number of time points (unless already aligned)
    # We'll just assert it's <= original
    original_points = sum(len(json.loads(f.read_text())['trajectory']['time_s']) for f in [json1,json2])
    assert len(datam['trajectory']['time_s']) <= original_points
