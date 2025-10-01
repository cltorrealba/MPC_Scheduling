"""Integration scaffolding between scheduling layer and fermentation control (Phase 4).

Dataclasses & helpers to bridge discrete scheduling and continuous fermentation.
Currently placeholders; logic will be enriched incrementally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Iterable
import pyomo.environ as pe


@dataclass
class FermentationStateSnapshot:
    time_s: float
    hold_up: float
    concentrations: Dict[str, float]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchedulingDemandProjection:
    demand: Dict[Tuple[str, int], float]
    horizon_periods: int
    meta: Dict[str, Any] = field(default_factory=dict)


def extract_state_snapshot(m, physical_time_scale: Optional[float] = None) -> FermentationStateSnapshot:
    try:
        final_time = pe.value(m.final_time) if hasattr(m, 'final_time') else 0.0
    except Exception:
        final_time = 0.0
    time_s = physical_time_scale if physical_time_scale is not None else final_time
    tau_last = getattr(m, 't').last() if hasattr(m, 't') else None
    concentrations = {}
    if tau_last is not None and hasattr(m, 'C'):
        for idx in getattr(m, 'j', []):
            try:
                concentrations[idx] = pe.value(m.C[tau_last, idx])
            except Exception:
                continue
    hold_up = 0.0
    if hasattr(m, 'M') and tau_last is not None:
        try:
            hold_up = pe.value(m.M[tau_last])
        except Exception:
            pass
    meta = {}
    if hasattr(m, 'route_config'):
        meta['routes'] = {r: int(pe.value(m.route_config[r])) for r in m.route_config}
    return FermentationStateSnapshot(time_s=time_s, hold_up=hold_up, concentrations=concentrations, meta=meta)


def derive_scheduling_demand(snapshot: FermentationStateSnapshot, target_states: List[str], periods: int, total_time_h: float) -> SchedulingDemandProjection:
    demand: Dict[Tuple[str, int], float] = {}
    if periods <= 0:
        raise ValueError("Periods must be positive")
    last_period = periods - 1
    for s in target_states:
        conc = snapshot.concentrations.get(s, 0.0)
        withdrawal = 0.05 * conc * snapshot.hold_up / 1000.0
        if withdrawal > 0:
            demand[(s, last_period)] = withdrawal
    meta = {'policy': 'proportional_last_period_5pct', 'source_time_s': snapshot.time_s, 'total_time_h': total_time_h}
    return SchedulingDemandProjection(demand=demand, horizon_periods=periods, meta=meta)


def stub_apply_schedule_to_fermentation(schedule_result: Any, fermentation_model) -> None:  # noqa: ANN401
    _ = (schedule_result, fermentation_model)
    return None


def apply_schedule_to_feeds(
    fermentation_model,
    scheduling_model,
    mapping: Dict[str, str],
    production_var: str = 'B',
    time_index: Iterable[int] | None = None,
    scale_factor: float = 1.0,
) -> int:
    """Map aggregate scheduled production into feed composition Cin of fermentation model.

    Parameters
    ----------
    fermentation_model : ConcreteModel
        Model built via build_fermentation_model with enable_mass_balance=True (Cin required).
    scheduling_model : ConcreteModel
        Scheduling Pyomo model result (minimal or durations) con variables de producción/batch.
    mapping : Dict[str,str]
        state_in_scheduling -> species_in_fermentation (e.g. {'C':'G'}).
    production_var : str, default 'B'
        Nombre de la variable batch/producción (para durations podría ser 'B_shift').
    time_index : iterable[int], optional
        Period indices to aggregate; default = all found in scheduling_model.T.
    scale_factor : float, default 1.0
        Factor multiplicativo para convertir unidades (si scheduling cantidades están en kg y Cin g/kg, etc.).

    Returns
    -------
    int
        Número de especies actualizadas en Cin.
    """
    if not hasattr(fermentation_model, 'Cin'):
        raise ValueError('Fermentation model must have enable_mass_balance=True to modify Cin')
    if not hasattr(scheduling_model, production_var):
        raise AttributeError(f'Scheduling model missing production var {production_var}')
    prod = getattr(scheduling_model, production_var)
    # Determine index structure: expect (task, unit, t)
    if time_index is None:
        if hasattr(scheduling_model, 'T'):
            time_index = list(scheduling_model.T.data())
        else:
            # Fallback: scan indices of production var for third position
            seen_t = set()
            for idx in prod:
                if isinstance(idx, tuple) and len(idx) >= 3:
                    seen_t.add(idx[-1])
            time_index = sorted(seen_t)
    updated = 0
    # Aggregate production per scheduling state using rho_prod if present
    agg: Dict[str, float] = {s: 0.0 for s in mapping.keys()}
    rho_prod = getattr(scheduling_model, 'rho_prod', None)
    for idx in prod:
        val = prod[idx].value
        if val is None or val <= 0:
            continue
        if not (isinstance(idx, tuple) and len(idx) >= 3):
            continue
        task, unit, t_idx = idx[0], idx[1], idx[2]
        if t_idx not in time_index:
            continue
        for sched_state in mapping.keys():
            weight = 1.0
            if rho_prod is not None:
                try:
                    weight = float(rho_prod[task, sched_state])
                except Exception:
                    weight = 0.0
            if weight <= 0:
                continue
            agg[sched_state] += float(val) * weight
    # Update Cin in fermentation model
    for sched_state, fer_sp in mapping.items():
        amount = agg.get(sched_state, 0.0) * scale_factor
        try:
            current = fermentation_model.Cin[fer_sp]
        except Exception:
            continue
        try:
            fermentation_model.Cin[fer_sp] = max(0.0, float(current) + amount)
            updated += 1
        except Exception:
            continue
    return updated


__all__ = [
    'FermentationStateSnapshot', 'SchedulingDemandProjection', 'extract_state_snapshot',
    'derive_scheduling_demand', 'stub_apply_schedule_to_fermentation', 'apply_schedule_to_feeds'
]


def adjust_feed_flows_in_fermentation(fermentation_model, scale: float = 1.0, cap: float | None = None) -> int:
    """Scale feed flow variables (F_C5liquid, F_liquified_fibers) by a factor.

    Negative scale factors are ignored. Returns number of variables updated.
    If cap provided, values are min(updated_value, cap).
    """
    if scale <= 0:
        return 0
    updated = 0
    for name in ['F_C5liquid','F_liquified_fibers']:
        if not hasattr(fermentation_model, name):
            continue
        var = getattr(fermentation_model, name)
        for t in getattr(fermentation_model, 't', []):
            try:
                base = var[t].value
                if base is None:
                    continue
                new_val = base * scale
                if cap is not None:
                    new_val = min(new_val, cap)
                var[t].set_value(new_val)
                updated += 1
            except Exception:
                continue
    return updated

