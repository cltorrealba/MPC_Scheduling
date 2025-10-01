from pathlib import Path
from biorefinery.models.scenario_loader import load_scenario
from biorefinery.models import FermentationConfig, SchedulingConfig


def test_load_example_basic():
    scenario_path = Path("biorefinery/scenarios/example_basic.json")
    scn = load_scenario(scenario_path)
    assert scn.name == "example_basic"
    assert isinstance(scn.fermentation, FermentationConfig)
    assert isinstance(scn.scheduling, SchedulingConfig)
    # Basic integrity checks
    assert scn.fermentation.horizon_h == 6.0
    assert scn.scheduling.n_periods == 6
    # Tasks mapped
    assert len(scn.scheduling.tasks) == 2
    # Demand mapping inside scheduling config
    assert scn.scheduling.demand.get(("C",5)) == 10.0
