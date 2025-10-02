import pyomo.environ as pe
import pytest

from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.models import TaskDef, UnitDef, SchedulingConfig, build_minimal_scheduling_model
from biorefinery.integration.scheduling_control_interface import apply_schedule_to_feeds


def test_apply_schedule_to_feeds_basic():
    # Fermentation model with mass balance to have Cin
    m_f = build_fermentation_model(include_kinetics=False, enable_mass_balance=True)
    # Inicialmente Cin especie 'G' debe existir y ser 0
    assert abs(pe.value(m_f.Cin['G'])) < 1e-12
    # Scheduling simple produce pseudo "G_state" mapeado a 'G'
    tasks = [TaskDef(name='ProdG', inputs={}, outputs={'G_state':1.0}, units=['U'], min_batch=5, max_batch=5, process_time_h=1.0)]
    units = [UnitDef(name='U')]
    states = ['G_state']
    cfg = SchedulingConfig(horizon_h=5.0, n_periods=5, tasks=tasks, units=units, states=states, initial_inventory={'G_state':0.0}, storage_capacity={'G_state':1000.0})
    sched_res = build_minimal_scheduling_model(cfg)
    m_s = sched_res.model
    # Activar lote en t=0
    m_s.X['ProdG','U',0].fix(1)
    m_s.B['ProdG','U',0].fix(5)
    for t in m_s.T:
        if t != 0:
            m_s.X['ProdG','U',t].fix(0)
            m_s.B['ProdG','U',t].fix(0)
    solver = pe.SolverFactory('glpk')
    if not solver.available(False):
        pytest.skip('glpk no disponible')
    solver.solve(m_s, tee=False)
    updated = apply_schedule_to_feeds(m_f, m_s, mapping={'G_state':'G'})
    assert updated == 1
    # Cin['G'] debe haber aumentado (igual al batch total producido * scale_factor=1)
    assert pe.value(m_f.Cin['G']) >= 5 - 1e-9


def test_apply_schedule_to_feeds_weighted():
    m_f = build_fermentation_model(include_kinetics=False, enable_mass_balance=True)
    tasks = [TaskDef(name='ProdMix', inputs={}, outputs={'G_state':0.6,'X_state':0.4}, units=['U'], min_batch=10, max_batch=10, process_time_h=1.0)]
    units = [UnitDef(name='U')]
    states = ['G_state','X_state']
    cfg = SchedulingConfig(horizon_h=5.0, n_periods=5, tasks=tasks, units=units, states=states,
                           initial_inventory={s:0.0 for s in states}, storage_capacity={s:1000.0 for s in states})
    sched_res = build_minimal_scheduling_model(cfg)
    m_s = sched_res.model
    m_s.X['ProdMix','U',0].fix(1); m_s.B['ProdMix','U',0].fix(10)
    for t in m_s.T:
        if t != 0:
            m_s.X['ProdMix','U',t].fix(0); m_s.B['ProdMix','U',t].fix(0)
    solver = pe.SolverFactory('glpk')
    if not solver.available(False):
        return
    solver.solve(m_s, tee=False)
    updated = apply_schedule_to_feeds(m_f, m_s, mapping={'G_state':'G','X_state':'X'})
    assert updated == 2
    # Cin 'G' should reflect 10*0.6 and Cin 'X' reflect 10*0.4 within tolerance
    assert abs(pe.value(m_f.Cin['G']) - 6.0) < 1e-6
    assert abs(pe.value(m_f.Cin['X']) - 4.0) < 1e-6
