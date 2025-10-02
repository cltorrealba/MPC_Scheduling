import subprocess, sys, csv, pathlib, shutil, json

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_empc_rolling.py'

def test_rolling_feedback_and_drift_window():
    log_dir = pathlib.Path('logs/feedback_empc')
    if log_dir.exists():
        shutil.rmtree(log_dir)
    args = [
        sys.executable, SCRIPT,
        '--total-horizon-h','8','--empc-step-h','2','--prediction-horizon-h','4',
        '--nfe-per-h','0.5','--log-dir', str(log_dir), '--store-json',
        '--exec-disturbance-alpha','0.05','--seed','222',
        '--economic-lambda','0.1','--economic-lambda2','0.05',
        '--export-drift-species','--fermentation-warm-start','--warm-start-schedule',
        '--feedback-scheduling-mode','all_species','--feedback-scheduling-scale','0.5',
        '--drift-window','2','--drift-alert-threshold','0.01'
    ]
    res = subprocess.run(args, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    csv_path = log_dir / 'rolling_performance_log.csv'
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 4  # 8 horizon / 2 step
    # New columns presence
    for col in ['economic_metric2','drift_l2_avg','drift_max_abs_avg','drift_l2_cum','drift_alert','schedule_feasible_flag','schedule_obj_value']:
        assert col in rows[0], f"Missing column {col}"
    # Rolling average after first step should reflect at most window size
    if rows[1]['drift_l2_avg'] not in ('', None):
        assert float(rows[1]['drift_l2_avg']) >= 0
    # Check species drift file
    drift_file = log_dir / 'drift_species_log.csv'
    assert drift_file.exists(), 'Drift species CSV not created (feedback test)'
    # Validate scheduling feedback inventory echo exists in JSON
    step0_json = json.load((log_dir/'steps'/'step_001.json').open())  # after first propagation
    sched_payload = step0_json['raw'].get('scheduling', {})
    assert 'initial_inventory_used' in sched_payload, 'Missing initial_inventory_used in scheduling payload'
