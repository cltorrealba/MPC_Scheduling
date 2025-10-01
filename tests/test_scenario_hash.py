from pathlib import Path
import json
from biorefinery.models.scenario_loader import load_scenario, compute_scenario_hash

def test_scenario_hash_stable(tmp_path: Path):
    scen_path = Path('biorefinery/scenarios/example_basic.json')
    scn = load_scenario(scen_path)
    h1 = scn.scenario_hash
    # Reload and ensure same hash
    scn2 = load_scenario(scen_path)
    assert h1 == scn2.scenario_hash
    # Modify a descriptive field only
    data = json.loads(scen_path.read_text(encoding='utf-8'))
    data['description'] = 'Changed description only'
    h2 = compute_scenario_hash(data)
    assert h2 == h1, 'Hash should NOT change when only description changes'
    # Change a functional field (horizon_h)
    data['fermentation']['horizon_h'] = data['fermentation']['horizon_h'] + 1.0
    h3 = compute_scenario_hash(data)
    assert h3 != h1, 'Hash MUST change when functional parameter changes'

