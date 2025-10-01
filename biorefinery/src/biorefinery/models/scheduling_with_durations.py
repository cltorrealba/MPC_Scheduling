from __future__ import annotations
"""Scheduling model with fixed discrete processing durations (multi-period tasks).

Approach:
- Each task-unit start at time t reserves the unit for tau[task,unit] consecutive periods.
- Consumption occurs at start; production is realized after the processing duration (end time) via a shifted batch variable.
- Objective placeholder (min starts) like minimal version.

Differences vs legacy full GDP:
- No disjunctions; tau is fixed per (task,unit) provided by configuration.
- No variable processing time; extension path available.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pyomo.environ as pe
import math

@dataclass
class DurationTaskDef:
    name: str
    inputs: Dict[str, float]
    outputs: Dict[str, float]
    units: List[str]
    min_batch: float
    max_batch: float
    process_time_h: float  # hours (continuous) -> will be mapped to discrete slots

@dataclass
class DurationSchedulingConfig:
    horizon_h: float = 12.0
    n_periods: int = 12
    tasks: List[DurationTaskDef] = field(default_factory=list)
    units: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    initial_inventory: Dict[str, float] = field(default_factory=dict)
    storage_capacity: Dict[str, float] = field(default_factory=dict)
    demand: Dict[Tuple[str,int], float] = field(default_factory=dict)
    objective: str = "min_starts"

@dataclass
class DurationSchedulingBuildResult:
    model: pe.ConcreteModel
    config: DurationSchedulingConfig
    discrete_duration_map: Dict[Tuple[str,str], int]


def build_scheduling_with_durations(cfg: DurationSchedulingConfig) -> DurationSchedulingBuildResult:
    m = pe.ConcreteModel(name="scheduling_with_durations")

    m.T = pe.RangeSet(0, cfg.n_periods - 1)
    m.Tasks = pe.Set(initialize=[t.name for t in cfg.tasks])
    m.Units = pe.Set(initialize=cfg.units)
    m.States = pe.Set(initialize=cfg.states)

    delta_h = cfg.horizon_h / max(1, cfg.n_periods)  # hours por periodo
    # Map processing time to integer slots (ceil to ensure feasibility)
    tau = {(t.name, u): math.ceil(t.process_time_h / delta_h) for t in cfg.tasks for u in cfg.units if u in t.units}
    # Eligibility & parameters
    m.eligible = pe.Param(m.Tasks, m.Units, initialize={(t.name,u): 1 if u in t.units else 0 for t in cfg.tasks for u in cfg.units}, within=pe.Binary, default=0)
    m.tau = pe.Param(m.Tasks, m.Units, initialize={(k1,k2): tau.get((k1,k2), 0) for k1 in m.Tasks for k2 in m.Units}, default=0)
    m.min_batch = pe.Param(m.Tasks, m.Units, initialize={(t.name,u): t.min_batch if u in t.units else 0 for t in cfg.tasks for u in cfg.units}, default=0.0)
    m.max_batch = pe.Param(m.Tasks, m.Units, initialize={(t.name,u): t.max_batch if u in t.units else 0 for t in cfg.tasks for u in cfg.units}, default=0.0)
    m.rho_cons = pe.Param(m.Tasks, m.States, initialize={(t.name,s): t.inputs.get(s,0.0) for t in cfg.tasks for s in cfg.states}, default=0.0)
    m.rho_prod = pe.Param(m.Tasks, m.States, initialize={(t.name,s): t.outputs.get(s,0.0) for t in cfg.tasks for s in cfg.states}, default=0.0)
    m.demand = pe.Param(m.States, m.T, initialize={(s,int(t)): cfg.demand.get((s,int(t)),0.0) for s in cfg.states for t in range(cfg.n_periods)}, default=0.0)
    m.S0 = pe.Param(m.States, initialize={s: cfg.initial_inventory.get(s,0.0) for s in cfg.states}, default=0.0)
    m.cap = pe.Param(m.States, initialize={s: cfg.storage_capacity.get(s, float("inf")) for s in cfg.states}, default=float("inf"))

    # Vars
    m.X = pe.Var(m.Tasks, m.Units, m.T, within=pe.Binary)
    m.B = pe.Var(m.Tasks, m.Units, m.T, within=pe.NonNegativeReals)
    m.B_shift = pe.Var(m.Tasks, m.Units, m.T, within=pe.NonNegativeReals)
    def inv_bounds(mdl,s,t):
        return (0.0, float(mdl.cap[s]))
    m.S = pe.Var(m.States, m.T, bounds=inv_bounds, within=pe.NonNegativeReals)

    # Capacity linking
    def cap_min(mdl,i,u,t):
        if pe.value(mdl.eligible[i,u]) < 0.5: return mdl.B[i,u,t] == 0
        return mdl.min_batch[i,u]*mdl.X[i,u,t] <= mdl.B[i,u,t]
    m.CapMin = pe.Constraint(m.Tasks,m.Units,m.T,rule=cap_min)
    def cap_max(mdl,i,u,t):
        if pe.value(mdl.eligible[i,u]) < 0.5: return mdl.B[i,u,t] == 0
        return mdl.B[i,u,t] <= mdl.max_batch[i,u]*mdl.X[i,u,t]
    m.CapMax = pe.Constraint(m.Tasks,m.Units,m.T,rule=cap_max)

    # Unit utilization with duration (sum of active tasks spanning t <= 1)
    def unit_util(mdl,u,t):
        return sum(mdl.X[i,u,tp] for i in mdl.Tasks for tp in mdl.T if pe.value(mdl.eligible[i,u])>0.5 and tp <= t and t < tp + mdl.tau[i,u]) <= 1
    m.UnitUtil = pe.Constraint(m.Units,m.T,rule=unit_util)

    # Shifted production: B_shift[i,u,t] = B[i,u,t - tau[i,u]] if t - tau >=0 else 0
    def shift_rule(mdl,i,u,t):
        tau_ = pe.value(mdl.tau[i,u])
        if tau_ == 0: # ineligible or zero time -> no shift
            return mdl.B_shift[i,u,t] == 0
        if t - tau_ >= 0:
            return mdl.B_shift[i,u,t] == mdl.B[i,u,t - tau_]
        return mdl.B_shift[i,u,t] == 0
    m.ShiftDef = pe.Constraint(m.Tasks,m.Units,m.T,rule=shift_rule)

    # Inventory: consumption at start; production when B_shift becomes available
    def inv_rule(mdl,s,t):
        cons_term = sum(mdl.rho_cons[i,s]*mdl.B[i,u,t] for i in mdl.Tasks for u in mdl.Units)
        prod_term = sum(mdl.rho_prod[i,s]*mdl.B_shift[i,u,t] for i in mdl.Tasks for u in mdl.Units)
        if t == 0:
            return mdl.S[s,t] == mdl.S0[s] + prod_term - cons_term - mdl.demand[s,t]
        return mdl.S[s,t] == mdl.S[s,t-1] + prod_term - cons_term - mdl.demand[s,t]
    m.Inventory = pe.Constraint(m.States,m.T,rule=inv_rule)

    # Objective placeholder
    def obj(mdl):
        return sum(mdl.X[i,u,t] for i in mdl.Tasks for u in mdl.Units for t in mdl.T)
    m.obj = pe.Objective(rule=obj, sense=pe.minimize)

    return DurationSchedulingBuildResult(model=m, config=cfg, discrete_duration_map={k:v for k,v in tau.items()})

__all__ = [
    "DurationTaskDef","DurationSchedulingConfig","DurationSchedulingBuildResult","build_scheduling_with_durations"
]
