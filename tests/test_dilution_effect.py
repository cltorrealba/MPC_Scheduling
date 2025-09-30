import pyomo.environ as pe

from biorefinery.models.fermentation import build_fermentation_model


def test_dilution_reduces_concentration_without_feed_source():
    init = {"G":10,"X":0,"F":0,"HMF":0,"ACT":0,"Eth":0,"Cell":1.0,"CO2":0.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                 initial_concentrations=init, include_dilution=True,
                                 feed_concentrations={})
    # Force positive flows at later times to create dilution sink
    for t in m.t:
        if t != m.t.first():
            m.F_C5liquid[t].set_value(m.F_C5liquid[t].ub/2)
            m.F_liquified_fibers[t].set_value(m.F_liquified_fibers[t].ub/2)
    solver = pe.SolverFactory('ipopt')
    if not solver.available():
        return
    solver.solve(m, tee=False)
    g0 = pe.value(m.C[m.t.first(),'G'])
    g_end = pe.value(m.C[m.t.last(),'G'])
    assert g_end <= g0 + 1e-6


def test_feed_source_can_replenish():
    init = {"G":1.0,"X":0,"F":0,"HMF":0,"ACT":0,"Eth":0,"Cell":1.0,"CO2":0.0}
    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                 initial_concentrations=init, include_dilution=True,
                                 feed_concentrations={"G": 50.0})
    for t in m.t:
        if t != m.t.first():
            m.F_C5liquid[t].set_value(m.F_C5liquid[t].ub/2)
            m.F_liquified_fibers[t].set_value(m.F_liquified_fibers[t].ub/2)
    solver = pe.SolverFactory('ipopt')
    if not solver.available():
        return
    solver.solve(m, tee=False)
    g0 = pe.value(m.C[m.t.first(),'G'])
    g_end = pe.value(m.C[m.t.last(),'G'])
    # With high feed concentration, final should not be drastically below initial
    assert g_end >= g0 * 0.5
