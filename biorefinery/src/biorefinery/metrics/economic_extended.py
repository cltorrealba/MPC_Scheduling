"""Extended economic metric: adds operating cost and energy penalty to base aggregate.

score_ext = alpha * base_score + beta * (1 - normalized_cost) + gamma * (1 - normalized_energy)
where parameters are weights normalized internally.
Costs/Energy are clipped and normalized by provided denominators.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from .economic_aggregate import compute_economic_aggregate, EconomicAggregateResult


@dataclass
class EconomicExtendedResult:
    score: float
    base: EconomicAggregateResult
    normalized_cost: float
    normalized_energy: float
    weights: Dict[str, float]


def compute_economic_extended(
    produced_ethanol_mass: float,
    theoretical_max_ethanol_mass: float,
    fulfilled_demand_mass: float,
    total_demand_mass: float,
    operating_cost: float,
    cost_normalizer: float,
    energy_use: float,
    energy_normalizer: float,
    weight_base: float = 0.5,
    weight_cost: float = 0.25,
    weight_energy: float = 0.25,
    weight_yield: float = 0.5,
    weight_demand: float = 0.5,
):
    base = compute_economic_aggregate(
        produced_ethanol_mass=produced_ethanol_mass,
        theoretical_max_ethanol_mass=theoretical_max_ethanol_mass,
        fulfilled_demand_mass=fulfilled_demand_mass,
        total_demand_mass=total_demand_mass,
        weight_yield=weight_yield,
        weight_demand=weight_demand,
    )
    if cost_normalizer <= 0 or energy_normalizer <= 0:
        raise ValueError('Normalizers must be positive')
    nc = min(1.0, max(0.0, operating_cost / cost_normalizer))
    ne = min(1.0, max(0.0, energy_use / energy_normalizer))
    total = weight_base + weight_cost + weight_energy
    wb = weight_base / total
    wc = weight_cost / total
    we = weight_energy / total
    score = wb * base.score + wc * (1 - nc) + we * (1 - ne)
    return EconomicExtendedResult(
        score=score,
        base=base,
        normalized_cost=nc,
        normalized_energy=ne,
        weights={'base': wb, 'cost': wc, 'energy': we}
    )

__all__ = ['compute_economic_extended','EconomicExtendedResult']