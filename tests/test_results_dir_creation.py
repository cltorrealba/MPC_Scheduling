import os, json, shutil, tempfile, subprocess, sys, pathlib

RUN_SCRIPT = 'biorefinery.scripts.run_enmpc'


def test_results_dir_creation_basic():
    tmp = tempfile.mkdtemp()
    try:
        results_dir = os.path.join(tmp, 'runA')
        cmd = [sys.executable, '-m', RUN_SCRIPT,
               '--total-time-h','12','--horizon-time-h','12','--step-time-h','6',
               '--nfe','2','--max-iterations','1','--warm-start',
               '--results-dir', results_dir,
               '--output','sample.json']
        # Run process
        subprocess.check_call(cmd)
        # Check directory and output
        assert os.path.isdir(results_dir)
        out_file = os.path.join(results_dir,'sample.json')
        assert os.path.isfile(out_file)
        with open(out_file,'r',encoding='utf-8') as f:
            data = json.load(f)
        assert 'meta' in data and 'trajectory' in data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
