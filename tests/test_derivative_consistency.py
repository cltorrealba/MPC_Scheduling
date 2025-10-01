import pytest
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.legacy.tolerances import series_tolerances

SPECIES = ['G','X','Eth']


def _pick_solver():
    for name in ('ipopt','glpk'):
        sf = pe.SolverFactory(name)
        if sf and sf.available(False):
            return name
    return None


def _finite_diff(series, times):
    # forward diff interior, last point replicate previous diff
    diffs = []
    for i in range(len(series)-1):
        dt = times[i+1] - times[i]
        if dt <= 0:
            diffs.append(None)
            continue
        diffs.append( (series[i+1]-series[i]) / dt )
    if diffs:
        diffs.append(diffs[-1])
    return diffs

def test_derivative_consistency():
    solver_name = _pick_solver()
    if solver_name is None:
        pytest.skip('Sin solver disponible para derivadas')
    solver = pe.SolverFactory(solver_name)

    m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                                 enable_mass_balance=False,  # use alternative balance block
                                 n_f_elements_t=4, total_f_elements_t=4,
                                 initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0})
    solver.solve(m, tee=False)

    times = sorted(list(m.t))
    t_float = [float(t) for t in times]

    # Extract concentration series
    series = {sp: [] for sp in SPECIES if (times[0], sp) in m.C}
    for t in times:
        for sp in list(series.keys()):
            try:
                series[sp].append(float(pe.value(m.C[t, sp])))
            except Exception:
                series[sp].append(None)

    # Compute finite difference derivatives
    fd = {sp: _finite_diff(vals, t_float) for sp, vals in series.items()}

    # Reconstruct derivative using alternative concentration balance equations (since enable_mass_balance=False)
    rec = {sp: [] for sp in series}
    for i, t in enumerate(times):
        for sp in rec:
            if t == m.t.first():
                rec[sp].append(None)
                continue
            val = None
            try:
                if sp == 'G' and (t,'G') in m.q:
                    val = -float(pe.value(m.q[t,'G'])) / pe.value(m.final_time)
                elif sp == 'X' and (t,'X') in m.q:
                    val = -float(pe.value(m.q[t,'X'])) / pe.value(m.final_time)
                elif sp == 'Eth' and (t,'Eth') in m.R:
                    val = float(pe.value(m.R[t,'Eth'])) / pe.value(m.final_time)
            except Exception:
                pass
            rec[sp].append(val)

    # Compare where both sides defined
    tol = series_tolerances()
    for sp in rec:
        if sp not in fd:
            continue
        diffs_fd = fd[sp]
        diffs_mod = rec[sp]
        for a,b in zip(diffs_fd, diffs_mod):
            if a is None or b is None:
                continue
            diff = abs(a - b)
            rel = diff / max(1e-6, abs(a))
            assert (diff <= tol.abs_tol) or (rel <= tol.rel_tol), f"Derivative mismatch {sp}: diff={diff:.3g} rel={rel:.3g} fd={a:.3g} model={b:.3g} (abs_tol={tol.abs_tol} rel_tol={tol.rel_tol})"
