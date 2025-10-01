import json, tempfile, os
from pathlib import Path
import importlib

def test_plot_enmpc_quick_basic(tmp_path: Path):
    # Create a minimal run JSON
    run_data = {
        "trajectory": {
            "time_s": [0, 3600, 7200],
            "species": {"G": [10,8,6], "X": [5,5.5,6], "Eth": [0,1,2], "Cell": [1,1,1], "CO2": [0,0.2,0.4]},
            "hold_up": [800, 820, 840]
        },
        "records": [
            {"t_start_s":0, "t_end_s":3600, "applied_control": {"F_liquified_fibers":0.1, "F_c5_feed":0.0}, "economic_metric": 1.0},
            {"t_start_s":3600, "t_end_s":7200, "applied_control": {"F_liquified_fibers":0.15}, "economic_metric": 2.0}
        ],
        "drift_metrics": {"mass_balance_error": [0.0, 0.001, 0.0005]}
    }
    run_path = tmp_path / "run.json"
    with run_path.open('w', encoding='utf-8') as f:
        json.dump(run_data, f)
    outdir = tmp_path / "figs"
    # Import module and call main via subprocess-like path
    mod = importlib.import_module('biorefinery.scripts.plot_enmpc_quick')
    # Simulate CLI
    import sys
    argv_backup = sys.argv
    sys.argv = ['plot_enmpc_quick','--run', str(run_path), '--outdir', str(outdir)]
    try:
        mod.main()
    finally:
        sys.argv = argv_backup
    # Assert at least one expected plot exists
    assert (outdir / 'concentrations_key.png').exists()
