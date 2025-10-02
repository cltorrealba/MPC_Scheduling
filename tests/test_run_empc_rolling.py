import csv, pathlib, json, subprocess, sys, shutil

DEF_CMD = [
    sys.executable,
    'biorefinery/src/biorefinery/scripts/run_empc_rolling.py',
    '--total-horizon-h','6',
    '--empc-step-h','2',
    '--prediction-horizon-h','4',
    '--nfe-per-h','0.5',
    '--log-dir','logs/test_empc_rolling',
    '--store-json',
    '--warm-start-schedule',
    '--exec-disturbance-alpha','0.05',
    '--seed','123'
]

def test_run_empc_rolling_smoke():
    # Run the rolling script (fails fast if returns non-zero)
    log_dir = pathlib.Path('logs/test_empc_rolling')
    if log_dir.exists():
        shutil.rmtree(log_dir)
    res = subprocess.run(DEF_CMD, capture_output=True, text=True)
    assert res.returncode == 0, f"Process failed: {res.stderr}\nSTDOUT:{res.stdout}"
    csv_path = pathlib.Path('logs/test_empc_rolling/rolling_performance_log.csv')
    assert csv_path.exists(), 'CSV not generated'
    rows = list(csv.DictReader(csv_path.open()))
    # Expect ceil(6/2)=3 steps
    assert len(rows) == 3, f"Unexpected number of steps: {len(rows)}"
    # Required columns
    required = {'step_index','t_start_h','t_end_h','predicted_end_h','final_ethanol_pred','feasible_flag','drift_l2','drift_max_abs'}
    assert required.issubset(rows[0].keys())
    # Monotonic t_start
    starts = [float(r['t_start_h']) for r in rows]
    assert starts == sorted(starts), 't_start_h not monotonic'
    # predicted_end_h should be >= t_end_h each step
    for r in rows:
        peh = float(r['predicted_end_h'])
        tend = float(r['t_end_h'])
        assert peh >= tend, 'predicted_end_h < t_end_h'
        # Drift metrics present and non-negative (if disturbance applied)
        if r.get('drift_l2') not in (None,''):
            assert float(r['drift_l2']) >= 0
            assert float(r['drift_max_abs']) >= 0
    # JSON step files
    for i in range(3):
        jf = pathlib.Path(f'logs/test_empc_rolling/steps/step_{i:03d}.json')
        assert jf.exists(), f'Missing step json {jf}'
        data = json.load(jf.open())
        assert 'final_state' in data['raw'] or 'raw' in data, 'Missing final_state in raw'
