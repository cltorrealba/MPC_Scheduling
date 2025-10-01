import pyomo.environ as pe
import pytest

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.integration.scheduling_control_interface import (
    extract_state_snapshot, derive_scheduling_demand
)
from biorefinery.models import (
    TaskDef, UnitDef, SchedulingConfig, build_minimal_scheduling_model
)


def _build_small_fermentation():
    m = build_fermentation_model(
        include_kinetics=True,
        detailed_kinetics=False,
        initial_concentrations={'G':10.0,'X':5.0,'Eth':0.0,'Cell':1.0,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0},
        enable_mass_balance=False  # keep light
    )
    # No solve (objective may be trivial). We just need current variable values for snapshot.
    return m


@pytest.mark.parametrize('target_states', [['Eth'], ['Eth','G']])
def test_round_trip_snapshot_to_scheduling(target_states):
    m = _build_small_fermentation()
    snap = extract_state_snapshot(m)
    # Derive a simple demand projection over 6 periods, 6h horizon placeholder
    projection = derive_scheduling_demand(snap, target_states=target_states, periods=6, total_time_h=6.0)
    # Build minimal scheduling model using the demand mapping
    tasks = [
        TaskDef(name='Ferment', inputs={}, outputs={s:1.0 for s in target_states}, units=['U1'], min_batch=1, max_batch=10, process_time_h=1.0)
    ]
    units = [UnitDef(name='U1')]
    states = list(set(target_states))
    demand = projection.demand
    cfg = SchedulingConfig(
        horizon_h=6.0,
        n_periods=6,
        tasks=tasks,
        units=units,
        states=states,
        initial_inventory={s:0.0 for s in states},
        storage_capacity={s:1000.0 for s in states},
        demand=demand
    )
    build_res = build_minimal_scheduling_model(cfg)
    sched_model = build_res.model
    solver = pe.SolverFactory('glpk')
    if not solver.available(False):
        pytest.skip('glpk no disponible')
    res = solver.solve(sched_model, tee=False)
    term = res.solver.termination_condition.value
    assert term in ('optimal','timeLimit','maxTimeLimit')
    # Verificar que si se generó demanda para un estado, la inventario final cumple la demanda
    for (s, t), dem in demand.items():
        assert pe.value(sched_model.S[s, t]) >= dem - 1e-8
