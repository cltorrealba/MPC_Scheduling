import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.integration.scheduling_control_interface import adjust_feed_flows_in_fermentation


def test_adjust_feed_flows_scale_and_cap():
    m = build_fermentation_model()
    t0 = m.t.first()
    base1 = pe.value(m.F_C5liquid[t0])
    base2 = pe.value(m.F_liquified_fibers[t0])
    updated = adjust_feed_flows_in_fermentation(m, scale=1.5, cap=2*base2)
    assert updated >= 2  # both series updated for all time points
    assert pe.value(m.F_C5liquid[t0]) == base1 * 1.5
    # cap not triggered because 1.5*base2 < 2*base2
    assert pe.value(m.F_liquified_fibers[t0]) == base2 * 1.5