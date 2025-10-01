import pyomo.environ as pe
from biorefinery.models import (
    DurationTaskDef, DurationSchedulingConfig, build_scheduling_with_durations
)

def test_duration_scheduling_shift():
    tasks = [
        DurationTaskDef(name="T1", inputs={"A":1.0}, outputs={"B":1.0}, units=["U"], min_batch=5, max_batch=5, process_time_h=2.0),
        DurationTaskDef(name="T2", inputs={"B":1.0}, outputs={"C":1.0}, units=["U"], min_batch=5, max_batch=5, process_time_h=2.0),
    ]
    cfg = DurationSchedulingConfig(
        horizon_h=8.0,
        n_periods=8,
        tasks=tasks,
        units=["U"],
        states=["A","B","C"],
        initial_inventory={"A":10.0},
        storage_capacity={s:100 for s in ["A","B","C"]},
        demand={("C",7):5.0}
    )
    res = build_scheduling_with_durations(cfg)
    m = res.model
    # Fix start decisions to create a pipeline: T1 at t=0, T2 at t=2 (after T1 duration=2)
    m.X["T1","U",0].fix(1); m.B["T1","U",0].fix(5)
    m.X["T2","U",2].fix(1); m.B["T2","U",2].fix(5)
    # All other X zero
    for t in m.T:
        if t!=0: m.X["T1","U",t].fix(0)
        if t!=2: m.X["T2","U",t].fix(0)
    solver = pe.SolverFactory("glpk")
    if not solver.available(False):
        return
    solver.solve(m, tee=False)
    # After solve, production of B from T1 should appear at t = 0 + tau(T1)
    tau_T1 = pe.value(m.tau["T1","U"])  # expect 2 periods
    t_prod_B = tau_T1
    assert pe.value(m.B_shift["T1","U",t_prod_B]) == 5
    # Consumption by T2 at t=2 reduces B, production of C appears at t = 2 + tau(T2)
    tau_T2 = pe.value(m.tau["T2","U"])  # expect 2
    t_prod_C = 2 + tau_T2
    if t_prod_C < cfg.n_periods:
        assert pe.value(m.B_shift["T2","U",t_prod_C]) == 5
