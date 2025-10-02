import subprocess, sys, csv, pathlib, shutil

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_empc_rolling.py'

def test_rolling_advanced_metrics():
    log_dir = pathlib.Path('logs/adv_empc')
    if log_dir.exists():
        shutil.rmtree(log_dir)
    args = [
        sys.executable, SCRIPT,
        '--total-horizon-h','6','--empc-step-h','2','--prediction-horizon-h','4',
        '--nfe-per-h','0.5','--log-dir', str(log_dir), '--store-json',
        '--exec-disturbance-alpha','0.05','--seed','111', '--economic-lambda','0.1',
        '--export-drift-species','--fermentation-warm-start','--warm-start-schedule'
    ]
    res = subprocess.run(args, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    csv_path = log_dir / 'rolling_performance_log.csv'
    rows = list(csv.DictReader(csv_path.open()))
    # economic_metric present
    assert 'economic_metric' in rows[0]
    # schedule_horizon_h and horizon_gap columns present
    assert 'schedule_horizon_h' in rows[0] and 'horizon_gap' in rows[0]
    # drift species file present
    drift_file = log_dir / 'drift_species_log.csv'
    assert drift_file.exists(), 'Drift species CSV not created'
    drift_rows = list(csv.reader(drift_file.open()))
    assert len(drift_rows) > 1  # header + at least one row
