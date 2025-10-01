"""Feed phase profile utilities for fermentation ENMPC.

Provides helpers to build piecewise feed schedules (inoculum / fed-batch / batch)
consistent with the legacy script, and to apply them to an existing Pyomo model
constructed with `enable_mass_balance=True`.

Design goals:
- Pure functions returning simple data structures (no hidden state)
- Model application separated (so tests can validate dict structure easily)
- Extensible: additional phases or control variables can be appended
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import pyomo.environ as pe

@dataclass(frozen=True)
class FeedPhase:
    name: str              # e.g. 'inoculum', 'fed_batch', 'batch'
    t_start_h: float       # start time in hours (absolute batch clock)
    t_end_h: float         # end time in hours (absolute batch clock)
    F_liquified_fibers: float  # base flow value (kg/s)
    F_C5liquid: float          # base flow value (kg/s)

DEFAULT_PHASES: List[FeedPhase] = [
    FeedPhase('inoculum', 0.0, 10.0, 2487*(1/60)*(1/60), 0.0),
    FeedPhase('fed_batch', 10.0, 70.0, 2487*(1/60)*(1/60), 628*(1/60)*(1/60)),
    FeedPhase('batch', 70.0, 190.0, 0.0, 0.0),
]


def build_phase_index(phases: List[FeedPhase]) -> List[FeedPhase]:
    # Validate ordering & non-overlap
    phases_sorted = sorted(phases, key=lambda p: p.t_start_h)
    last_end = -1e-9
    for ph in phases_sorted:
        assert ph.t_start_h >= last_end - 1e-9, "Phases overlap or out of order"
        assert ph.t_end_h > ph.t_start_h, "Phase duration must be positive"
        last_end = ph.t_end_h
    return phases_sorted


def phase_for_time(phases: List[FeedPhase], t_h: float) -> FeedPhase:
    for ph in phases:
        if ph.t_start_h <= t_h < ph.t_end_h:
            return ph
    # If exactly at final end, return last
    return phases[-1]


def generate_feed_trajectories(phases: List[FeedPhase], time_points_s: List[float]) -> Dict[str, List[float]]:
    """Return dictionaries with flows aligned with given absolute time points (seconds)."""
    phases_idx = build_phase_index(phases)
    traj_F_fibers = []
    traj_F_C5 = []
    for t_s in time_points_s:
        t_h = t_s / 3600.0
        ph = phase_for_time(phases_idx, t_h)
        traj_F_fibers.append(ph.F_liquified_fibers)
        traj_F_C5.append(ph.F_C5liquid)
    return {
        'F_liquified_fibers': traj_F_fibers,
        'F_C5liquid': traj_F_C5,
    }


def apply_feed_profile(m: pe.ConcreteModel, phases: Optional[List[FeedPhase]] = None, override_existing: bool = True) -> None:
    """Apply phase profile values to model feed variables for current horizon.

    Assumes model has attributes: t, current_starting_time, current_final_time,
    F_liquified_fibers, F_C5liquid. The time set is normalized [0,1]; absolute
    time = current_starting_time + tau*(current_final_time-current_starting_time).
    """
    if phases is None:
        phases = DEFAULT_PHASES
    phases_idx = build_phase_index(phases)
    for tau in m.t:
        abs_t = pe.value(m.current_starting_time) + float(tau) * (pe.value(m.current_final_time) - pe.value(m.current_starting_time))
        t_h = abs_t / 3600.0
        ph = phase_for_time(phases_idx, t_h)
        if override_existing or (m.F_liquified_fibers[tau].value is None):
            m.F_liquified_fibers[tau].value = ph.F_liquified_fibers
        if override_existing or (m.F_C5liquid[tau].value is None):
            m.F_C5liquid[tau].value = ph.F_C5liquid

__all__ = [
    'FeedPhase',
    'DEFAULT_PHASES',
    'build_phase_index',
    'phase_for_time',
    'generate_feed_trajectories',
    'apply_feed_profile',
]
