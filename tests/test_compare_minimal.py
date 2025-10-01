import json, subprocess, sys, pathlib

# Minimal smoke test: run with very small nfe and horizon to validate JSON structure

def test_compare_structure(tmp_path):
    out = tmp_path / 'cmp.json'
    cmd = [sys.executable, '-m', 'biorefinery.scripts.compare_legacy_vs_modular', '--horizon-h', '1', '--nfe', '1', '--sched-periods', '1', '--output', str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Process failed: {res.stderr}\nSTDOUT: {res.stdout}"
    assert out.exists(), "Output JSON not created"
    data = json.loads(out.read_text(encoding='utf-8'))
    for key in ['modular','legacy','comparison','meta']:
        assert key in data, f"Missing section {key}"
    # Basic KPI presence
    mod = data['modular']
    assert 'final_hold_up' in mod.get('kpis', mod)
    assert 'final_ethanol_conc' in mod.get('kpis', mod)
