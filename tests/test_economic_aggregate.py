from biorefinery.metrics.economic_aggregate import compute_economic_aggregate


def test_economic_aggregate_balanced():
    res = compute_economic_aggregate(
        produced_ethanol_mass=80,
        theoretical_max_ethanol_mass=100,
        fulfilled_demand_mass=45,
        total_demand_mass=50,
        weight_yield=0.5,
        weight_demand=0.5,
        meta={'scenario':'demo'}
    )
    assert 0 <= res.score <= 1
    assert abs(res.yield_fraction - 0.8) < 1e-12
    assert abs(res.demand_fraction - 0.9) < 1e-12
    # Score should be average of 0.8 and 0.9 = 0.85
    assert abs(res.score - 0.85) < 1e-12


def test_economic_aggregate_weighting():
    res = compute_economic_aggregate(
        produced_ethanol_mass=80,
        theoretical_max_ethanol_mass=100,
        fulfilled_demand_mass=45,
        total_demand_mass=50,
        weight_yield=0.8,
        weight_demand=0.2,
    )
    # Normalized weights: yield=0.8, demand=0.2 -> score = 0.8*0.8 + 0.2*0.9 = 0.64 + 0.18 = 0.82
    assert abs(res.score - 0.82) < 1e-12
