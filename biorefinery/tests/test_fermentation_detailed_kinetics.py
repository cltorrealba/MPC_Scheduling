import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model

@pytest.mark.parametrize("detailed", [True, False])
def test_detailed_kinetics_parameters_and_constraints(detailed):
    m = build_fermentation_model(n_f_elements_t=2, total_f_elements_t=10, include_kinetics=True, detailed_kinetics=detailed)
    # Core newly added params must exist regardless of detailed flag (they are defined outside conditional)
    for p in [
        'K0F','K1F','K2F','K0HMF','K1HMF','K2HMF','K0ACT','K1ACT','K2ACT',
        'PMP_F','gamma_F','PMP_HMF','gamma_HMF','PMP_ACT','gamma_ACT'
    ]:
        assert hasattr(m, p), f"Missing parameter {p}"
    if detailed:
        # Expect detailed constraint component names
        for cname in ['q_glucose_rate','q_xylose_rate','q_furfural_rate','q_hmf_rate','q_acetate_rate']:
            assert hasattr(m, cname), f"Missing detailed constraint {cname}"
    else:
        # Simplified versions should exist, detailed ones absent
        for cname in ['qG_simple','qX_simple','qF_simple','qHMF_simple','qACT_simple']:
            assert hasattr(m, cname), f"Missing simplified constraint {cname}"
        for absent in ['q_furfural_rate','q_hmf_rate','q_acetate_rate']:
            assert not hasattr(m, absent), f"Constraint {absent} should not be present without detailed kinetics"

    # Build model should be solvable at least for creation (no solve here)
    assert isinstance(m, pe.ConcreteModel)
