import json, os, math, tempfile, shutil
from pathlib import Path
import subprocess, sys

SCRIPT = 'biorefinery.scripts.run_dsda_multistart'

PY = sys.executable


def run_cmd(args, cwd):
    cp = subprocess.run([PY, '-m', SCRIPT] + args, cwd=cwd, capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    txt = cp.stdout.splitlines()
    # Primer linea que empieza con '{' es comienzo del JSON del resultado
    for i,line in enumerate(txt):
        if line.startswith('{'):
            candidate = '\n'.join(txt[i:])
            return json.loads(candidate)
    raise AssertionError('No JSON object found')


def test_cache_accumulates(tmp_path):
    cache_file = tmp_path / 'dsda_cache.json'
    # Primera corrida: 3 starts
    res1 = run_cmd(['--starts','3','--cache', str(cache_file),'--nfe','1','--horizon-h','2'], cwd=os.getcwd())
    assert len(res1['entries']) == 3
    # Segunda corrida: otras 2 nuevas
    res2 = run_cmd(['--starts','2','--cache', str(cache_file),'--nfe','1','--horizon-h','2'], cwd=os.getcwd())
    assert len(res2['entries']) == 5
    # Tercera corrida exhaustiva (debe llegar a 32)
    res3 = run_cmd(['--exhaustive','--cache', str(cache_file),'--nfe','1','--horizon-h','2'], cwd=os.getcwd())
    assert len(res3['entries']) == 32
    # Best presente
    assert res3['best'] is not None
    assert 'objective' in res3['best']
