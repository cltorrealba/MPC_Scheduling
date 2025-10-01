import os, tempfile, json, subprocess, sys, zipfile, glob, time

CLEAN = 'biorefinery.scripts.clean_outputs'
SNAP = 'biorefinery.scripts.snapshot_results'
RUN = 'biorefinery.scripts.run_enmpc'


def _run(cmd):
    subprocess.check_call(cmd)


def test_snapshot_and_cleanup_flow():
    tmp = tempfile.mkdtemp()
    try:
        results = os.path.join(tmp, 'results')
        os.makedirs(results, exist_ok=True)
        # Generate two small runs
        _run([sys.executable,'-m',RUN,'--total-time-h','12','--horizon-time-h','12','--step-time-h','6','--nfe','2','--max-iterations','1','--results-dir',results,'--output','r1.json'])
        time.sleep(1)
        _run([sys.executable,'-m',RUN,'--total-time-h','12','--horizon-time-h','12','--step-time-h','6','--nfe','2','--max-iterations','1','--results-dir',results,'--output','r2.json'])
        json_files = glob.glob(os.path.join(results,'*.json'))
        assert len(json_files) >= 2
        # Snapshot dry-run
        _run([sys.executable,'-m',SNAP,'--inputs',results,'--patterns','*.json','--output',os.path.join(tmp,'snap.zip'),'--dry-run'])
        # Create snapshot
        _run([sys.executable,'-m',SNAP,'--inputs',results,'--patterns','*.json','--output',os.path.join(tmp,'snap.zip')])
        assert os.path.isfile(os.path.join(tmp,'snap.zip'))
        with zipfile.ZipFile(os.path.join(tmp,'snap.zip'),'r') as zf:
            assert 'MANIFEST.json' in zf.namelist()
            manifest = json.loads(zf.read('MANIFEST.json'))
            assert 'manifest_hash' in manifest
        # Cleanup: keep latest 1, delete rest
        _run([sys.executable,'-m',CLEAN,'--paths',results,'--patterns','*.json','--keep-latest','1'])
        remaining = glob.glob(os.path.join(results,'*.json'))
        assert len(remaining) == 1
    finally:
        pass  # tmp removed by test harness or left for inspection
