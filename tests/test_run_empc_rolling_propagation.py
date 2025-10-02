import subprocess, sys, csv, pathlib, shutil, json

SCRIPT = 'biorefinery/src/biorefinery/scripts/run_empc_rolling.py'
BASE_ARGS = ['--total-horizon-h','4','--empc-step-h','2','--prediction-horizon-h','3','--nfe-per-h','0.5','--log-dir','{log}','--seed','42','--exec-disturbance-alpha','0.05','--store-json']

MODES = ['final','applied','realized']

def run_mode(mode):
    log_dir = pathlib.Path(f'logs/propagation_{mode}')
    if log_dir.exists():
        shutil.rmtree(log_dir)
    args = [sys.executable, SCRIPT] + [a.format(log=str(log_dir)) for a in BASE_ARGS] + ['--propagation-mode', mode]
    res = subprocess.run(args, capture_output=True, text=True)
    assert res.returncode == 0, f"Mode {mode} failed: {res.stderr}\nSTDOUT:{res.stdout}"
    csv_path = log_dir / 'rolling_performance_log.csv'
    rows = list(csv.DictReader(csv_path.open()))
    # Expect ceil(4/2)=2 steps
    assert len(rows) == 2
    # propagation_mode column constant
    assert all(r['propagation_mode']==mode for r in rows)
    # predicted_end_h monotonic
    preds = [float(r['predicted_end_h']) for r in rows]
    assert preds == sorted(preds)
    # JSON integrity
    step0 = json.load((log_dir/'steps'/'step_000.json').open())
    assert 'raw' in step0 and 'final_state' in step0['raw']


def test_propagation_modes():
    for m in MODES:
        run_mode(m)
