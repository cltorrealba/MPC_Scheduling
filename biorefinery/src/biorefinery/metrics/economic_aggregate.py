"""Aggregate economic metric combining ethanol yield and scheduling demand fulfillment.

Formula (normalized weighted sum):
    score = w_yield * Y + w_demand * D
where
    Y = (produced_ethanol_mass / theoretical_max_ethanol_mass)
    D = (fulfilled_demand_mass / total_demand_mass)
Weights default to 0.5 / 0.5 and both components are clipped to [0,1].
Return structure includes component breakdown for transparency.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class EconomicAggregateResult:
    score: float
    yield_fraction: float
    demand_fraction: float
    produced_ethanol_mass: float
    theoretical_max_ethanol_mass: float
    fulfilled_demand_mass: float
    total_demand_mass: float
    weights: Dict[str, float]
    meta: Dict[str, Any]


def compute_economic_aggregate(
    produced_ethanol_mass: float,
    theoretical_max_ethanol_mass: float,
    fulfilled_demand_mass: float,
    total_demand_mass: float,
    weight_yield: float = 0.5,
    weight_demand: float = 0.5,
    meta: Dict[str, Any] | None = None,
) -> EconomicAggregateResult:
    if theoretical_max_ethanol_mass <= 0 or total_demand_mass <= 0:
        raise ValueError("Theoretical max and total demand must be positive")
    Y = max(0.0, min(1.0, produced_ethanol_mass / theoretical_max_ethanol_mass))
    D = max(0.0, min(1.0, fulfilled_demand_mass / total_demand_mass))
    norm = weight_yield + weight_demand
    if norm <= 0:
        raise ValueError("Sum of weights must be positive")
    wy = weight_yield / norm
    wd = weight_demand / norm
    score = wy * Y + wd * D
    return EconomicAggregateResult(
        score=score,
        yield_fraction=Y,
        demand_fraction=D,
        produced_ethanol_mass=produced_ethanol_mass,
        theoretical_max_ethanol_mass=theoretical_max_ethanol_mass,
        fulfilled_demand_mass=fulfilled_demand_mass,
        total_demand_mass=total_demand_mass,
        weights={'yield': wy, 'demand': wd},
        meta=meta or {},
    )

__all__ = [
    'compute_economic_aggregate', 'EconomicAggregateResult'
]