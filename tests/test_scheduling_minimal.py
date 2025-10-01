import pyomo.environ as pe
from biorefinery.models import (
    TaskDef, UnitDef, SchedulingConfig, build_minimal_scheduling_model
)

def test_minimal_scheduling_feasible():
    tasks = [
        TaskDef(name="T1", inputs={"A":1.0}, outputs={"B":1.0}, units=["U1"], min_batch=5, max_batch=10, process_time_h=1.0),
        TaskDef(name="T2", inputs={"B":1.0}, outputs={"C":1.0}, units=["U1"], min_batch=5, max_batch=10, process_time_h=1.0),
    ]
    units = [UnitDef(name="U1")]
    states = ["A","B","C"]
    cfg = SchedulingConfig(
        horizon_h=6.0,
        n_periods=6,
        tasks=tasks,
        units=units,
        states=states,
        initial_inventory={"A":50.0},
        storage_capacity={s:1000 for s in states},
        demand={("C",5):10.0}
    )
    result = build_minimal_scheduling_model(cfg)
    m = result.model
    solver = pe.SolverFactory("glpk")
    if not solver.available(False):
        # Skip if solver not present in environment
        return
    res = solver.solve(m, tee=False)
    assert res.solver.termination_condition.value in ("optimal","timeLimit","maxTimeLimit")
    # Ensure demand satisfied at final period if inventory of C >= demand
    assert pe.value(m.S["C",5]) >= 10.0

