from __future__ import annotations
"""
Minimal scheduling abstraction decoupled from legacy formulations.
Focus: discrete-time horizon, unit-task assignment with capacity & inventory balance skeleton.
This intentionally covers only a stable, small surface to allow future integration with MPC.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import pyomo.environ as pe

# ---------------------- Data Contracts ----------------------
@dataclass
class TaskDef:
    name: str
    inputs: Dict[str, float]  # state -> fraction consumed per batch (normalized basis)
    outputs: Dict[str, float]  # state -> fraction produced per batch
    units: List[str]  # compatible units
    min_batch: float
    max_batch: float
    process_time_h: float  # nominal fixed processing time (h)

@dataclass
class UnitDef:
    name: str
    kind: Optional[str] = None

@dataclass
class SchedulingConfig:
    horizon_h: float = 12.0
    n_periods: int = 12  # equally spaced discrete periods
    tasks: List[TaskDef] = field(default_factory=list)
    units: List[UnitDef] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    initial_inventory: Dict[str, float] = field(default_factory=dict)
    storage_capacity: Dict[str, float] = field(default_factory=dict)
    demand: Dict[Tuple[str,int], float] = field(default_factory=dict)  # (state, t_index) -> required withdrawal
    objective: str = "cost_min"  # future extension

@dataclass
class SchedulingBuildResult:
    model: pe.ConcreteModel
    config: SchedulingConfig
    time_points: List[int]
    task_names: List[str]
    unit_names: List[str]
    state_names: List[str]

# ---------------------- Builder ----------------------

def build_minimal_scheduling_model(cfg: SchedulingConfig) -> SchedulingBuildResult:
    m = pe.ConcreteModel(name="scheduling_minimal")

    # Sets
    m.T = pe.RangeSet(0, cfg.n_periods - 1)
    m.Tasks = pe.Set(initialize=[t.name for t in cfg.tasks])
    m.Units = pe.Set(initialize=[u.name for u in cfg.units])
    m.States = pe.Set(initialize=cfg.states)

    # Parameters (maps)
    # Task-unit eligibility
    eligibility = {(t.name, u): 1 if u in t.units else 0 for t in cfg.tasks for u in m.Units}
    m.eligible = pe.Param(m.Tasks, m.Units, initialize=eligibility, within=pe.Binary, mutable=False)

    min_batch = {(t.name, u): t.min_batch if u in t.units else 0.0 for t in cfg.tasks for u in m.Units}
    max_batch = {(t.name, u): t.max_batch if u in t.units else 0.0 for t in cfg.tasks for u in m.Units}
    m.min_batch = pe.Param(m.Tasks, m.Units, initialize=min_batch, default=0.0)
    m.max_batch = pe.Param(m.Tasks, m.Units, initialize=max_batch, default=0.0)

    # Fractions
    cons = {(t.name, s): t.inputs.get(s, 0.0) for t in cfg.tasks for s in m.States}
    prod = {(t.name, s): t.outputs.get(s, 0.0) for t in cfg.tasks for s in m.States}
    m.rho_cons = pe.Param(m.Tasks, m.States, initialize=cons, default=0.0)
    m.rho_prod = pe.Param(m.Tasks, m.States, initialize=prod, default=0.0)

    demand = {(s, int(t)): cfg.demand.get((s, int(t)), 0.0) for s in m.States for t in m.T}
    m.demand = pe.Param(m.States, m.T, initialize=demand, default=0.0)

    init_inv = {s: cfg.initial_inventory.get(s, 0.0) for s in m.States}
    m.S0 = pe.Param(m.States, initialize=init_inv, default=0.0)
    cap = {s: cfg.storage_capacity.get(s, float("inf")) for s in m.States}
    # Pyomo does not like inf upper bounds -> store separately
    m.cap = pe.Param(m.States, initialize=cap)

    # Variables
    m.X = pe.Var(m.Tasks, m.Units, m.T, within=pe.Binary)  # start decision
    m.B = pe.Var(m.Tasks, m.Units, m.T, within=pe.NonNegativeReals)  # batch size executed at period start
    def inv_bounds(mdl, s, t):
        return (0.0, float(mdl.cap[s]))
    m.S = pe.Var(m.States, m.T, bounds=inv_bounds, within=pe.NonNegativeReals)

    # Capacity linking (if start -> batch within bounds)
    def capacity_min_rule(mdl, task, unit, t):
        if pe.value(mdl.eligible[task, unit]) < 0.5:
            return mdl.B[task, unit, t] == 0
        return mdl.min_batch[task, unit] * mdl.X[task, unit, t] <= mdl.B[task, unit, t]
    m.CapacityMin = pe.Constraint(m.Tasks, m.Units, m.T, rule=capacity_min_rule)

    def capacity_max_rule(mdl, task, unit, t):
        if pe.value(mdl.eligible[task, unit]) < 0.5:
            return mdl.B[task, unit, t] == 0
        return mdl.B[task, unit, t] <= mdl.max_batch[task, unit] * mdl.X[task, unit, t]
    m.CapacityMax = pe.Constraint(m.Tasks, m.Units, m.T, rule=capacity_max_rule)

    # Unit cannot run two tasks simultaneously (no duration modeling yet -> single slot per period)
    def unit_util_rule(mdl, unit, t):
        return sum(mdl.X[task, unit, t] for task in mdl.Tasks if pe.value(mdl.eligible[task, unit]) > 0.5) <= 1
    m.UnitUtil = pe.Constraint(m.Units, m.T, rule=unit_util_rule)

    # Inventory balance (instantaneous batch completion inside period)
    def inv_balance_rule(mdl, s, t):
        if t == 0:
            return mdl.S[s, t] == mdl.S0[s] + sum(mdl.rho_prod[task, s] * mdl.B[task, unit, t]
                                                  - mdl.rho_cons[task, s] * mdl.B[task, unit, t]
                                                  for task in mdl.Tasks for unit in mdl.Units) - mdl.demand[s, t]
        return mdl.S[s, t] == mdl.S[s, t-1] + sum(mdl.rho_prod[task, s] * mdl.B[task, unit, t]
                                                  - mdl.rho_cons[task, s] * mdl.B[task, unit, t]
                                                  for task in mdl.Tasks for unit in mdl.Units) - mdl.demand[s, t]
    m.InventoryBalance = pe.Constraint(m.States, m.T, rule=inv_balance_rule)

    # Placeholder cost (minimize total number of starts) for feasibility focus
    def obj_rule(mdl):
        return sum(mdl.X[task, unit, t] for task in mdl.Tasks for unit in mdl.Units for t in mdl.T)
    m.obj = pe.Objective(rule=obj_rule, sense=pe.minimize)

    return SchedulingBuildResult(
        model=m,
        config=cfg,
        time_points=list(m.T.data()),
        task_names=list(m.Tasks.data()),
        unit_names=list(m.Units.data()),
        state_names=list(m.States.data()),
    )

__all__ = [
    "TaskDef","UnitDef","SchedulingConfig","SchedulingBuildResult","build_minimal_scheduling_model"
]
