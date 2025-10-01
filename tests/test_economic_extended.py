from biorefinery.metrics.economic_extended import compute_economic_extended


def test_economic_extended_balanced():
    res = compute_economic_extended(
        produced_ethanol_mass=80,
        theoretical_max_ethanol_mass=100,
        fulfilled_demand_mass=45,
        total_demand_mass=50,
        operating_cost=400,
        cost_normalizer=1000,
        energy_use=300,
        energy_normalizer=1000,
        weight_base=0.5,
        weight_cost=0.25,
        weight_energy=0.25,
        weight_yield=0.5,
        weight_demand=0.5,
    )
    assert 0 <= res.score <= 1
    # Normalized cost = 0.4 => (1 - 0.4)=0.6 ; energy 0.3 => (1-0.3)=0.7
    # base.score from aggregate: yield=0.8, demand=0.9 => 0.85
    # score = 0.5*0.85 + 0.25*0.6 + 0.25*0.7 = 0.425 + 0.15 + 0.175 = 0.75
    assert abs(res.score - 0.75) < 1e-12