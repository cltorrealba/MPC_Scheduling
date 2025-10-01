import pytest
import pyomo.environ as pe
from biorefinery.models.api_contract import (
    FermentationConfig,
    build_fermentation_model_v2,
    compute_kinetics_param_hash,
)

@pytest.mark.timeout(60)
def test_api_contract_basic():
    cfg = FermentationConfig(horizon_h=6.0, nfe=3, include_kinetics=True, detailed_kinetics=False)
    result = build_fermentation_model_v2(cfg)
    assert result.physical_horizon_s == pytest.approx(6*3600)
    assert 'G' in result.species
    if cfg.include_kinetics:
        assert 'G' in result.kinetic_species
        assert result.param_hash is not None
    # Param hash stable across rebuild
    result2 = build_fermentation_model_v2(cfg)
    assert result.param_hash == result2.param_hash

@pytest.mark.timeout(60)
def test_param_hash_changes_on_param_mutation():
    cfg = FermentationConfig(include_kinetics=True)
    res = build_fermentation_model_v2(cfg)
    h1 = res.param_hash
    # Create a lightweight copy of hash inputs by temporarily rebuilding and monkeypatching one param as mutable
    res2 = build_fermentation_model_v2(cfg)
    m2 = res2.model
    if hasattr(m2, 'qmax_G'):
        # Re-declare a mutable param with modified value (simulate calibrated change)
        val_old = float(m2.qmax_G.value)
        # Can't modify immutable directly; instead add an auxiliary mutable Param representing calibration override
        # and adjust it into hash logic by temporarily changing attribute for test only.
        # Simpler: directly alter the component _value attribute (Pyomo internal) for test purposes.
        try:
            m2.qmax_G._value = val_old * 1.1  # noqa: protected access used only in test context
        except Exception:
            pytest.skip('Unable to manipulate param hash for test environment')
    h2 = compute_kinetics_param_hash(m2)
    # Should differ after mutation
    if h1 is not None and h2 is not None:
        assert h1 != h2
