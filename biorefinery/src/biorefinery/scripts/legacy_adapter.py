import json
import traceback
from typing import Dict, Any, Optional

import pyomo.environ as pe

from biorefinery.optimization.solvers import pick_available_solver

# We delay heavy legacy import until function call to avoid side-effect imports at module load

def _import_legacy_build():
    try:
        from biorefinery_models.Fermentation_Scheduling_and_MPC import (
            build_fermentation_one_time_step_new, objective_function as _legacy_objective_function  # type: ignore
        )
        return build_fermentation_one_time_step_new, _legacy_objective_function
    except Exception as e:
        raise ImportError(f"Failed importing legacy build function: {e}")


def run_legacy_single_step(
    total_sim_time: float = 190*60*60,
    total_f_elements_t: int = 50,
    n_f_elements_t: int = 1,
    solver: Optional[str] = None,
    tee: bool = False,
    regularize: bool = False,
    epsilon: float = 1e-6,
    floor_M: float | None = None,
    floor_C: float | None = None,
    warmstart: bool = False,
    add_mass_slack: bool = False,
    slack_weight: float = 1e3,
    cap_M: float | None = None,
    diagnostics: bool = False,
    diagnostics_top: int = 10,
    initial_mass_slack: bool = False,
    initial_slack_weight: float = 1e5,
    # New stabilization features
    feed_align: bool = False,
    feed_slack: bool = False,
    feed_slack_weight: float = 1e5,
    smooth_fin_weight: float = 0.0,
    align_modular_init: bool = False,
    scale_model: bool = False,
    simple_feed: bool = False,
    simple_feed_rate: float | None = None,
    normalized_feed: bool = False,
    normalized_feed_scale: bool = False,
    ipopt_max_iter: int | None = None,
    ipopt_tol: float | None = None,
    ipopt_acceptable_tol: float | None = None,
    ipopt_print_level: int | None = None,
    ipopt_linear_solver: str | None = None,
    ipopt_bound_relax_factor: float | None = None,
    ipopt_constr_viol_tol: float | None = None,
    normalized_feed_slack: bool = False,
    normalized_feed_slack_weight: float = 1e6,
    normalized_feed_micro_slack: bool = False,
    normalized_feed_micro_slack_budget: float = 0.01,
    normalized_feed_micro_slack_weight: float = 1e8,
    sync_fin_initial: bool = False,
    jitter_conc: bool = False,
    jitter_conc_mag: float = 1e-5,
    jitter_seed: int | None = None,
    relax_initial_comp: bool = False,
) -> Dict[str, Any]:
    """Build and solve a minimal legacy one-step fermentation model and extract KPIs.

    Returns dict with: status, final_ethanol_conc, final_hold_up, objective, solver_name, nfe
    """
    try:
        build_fn, legacy_objective_function = _import_legacy_build()
    except Exception as e:
        return {"status": "import_error", "error": str(e)}

    try:
        m = build_fn(total_sim_time=total_sim_time,
                     discretization='collocation',
                     n_f_elements_t=n_f_elements_t,
                     total_f_elements_t=total_f_elements_t)
    except Exception as e:
        return {"status": "build_error", "error": str(e)}

    # Optional regularization to avoid pow'(0, alpha<1) gradient issues
    if regularize:
        # 1. Adjust parameters with fractional exponents < 1 (gamma_X, gamma_G) if present
        for pname in ("gamma_X", "gamma_G"):
            if hasattr(m, pname):
                p = getattr(m, pname)
                try:
                    if pe.value(p) < 1.0:
                        p.set_value(1.0)
                except Exception:
                    pass
        # 2. Add small epsilon to any concentration variables or params at zero that could appear in denominators / powers
        if hasattr(m, 'C'):
            for (t,j) in list(m.C.index_set()):  # type: ignore
                try:
                    if m.C[t,j].value is not None and m.C[t,j].value == 0:
                        m.C[t,j].value = epsilon
                except Exception:
                    continue
        if hasattr(m, 'C0'):
            for j in m.C0:
                try:
                    if m.C0[j].value == 0:
                        m.C0[j].value = epsilon
                except Exception:
                    pass

    # Apply floors (bounds tightening) if requested
    if floor_M is not None and hasattr(m, 'M'):
        for t in m.t:
            try:
                m.M[t].setlb(floor_M)
                if m.M[t].value is not None and m.M[t].value < floor_M:
                    m.M[t].value = floor_M
            except Exception:
                continue
        # Also raise initial mass parameters to floor to avoid artificial infeasibility
        for pname in ('M0','M0_prev'):
            if hasattr(m, pname):
                try:
                    p = getattr(m, pname)
                    if pe.value(p) < floor_M:
                        p.set_value(floor_M)
                except Exception:
                    pass
    # Apply cap if requested
    if cap_M is not None and hasattr(m, 'M'):
        for t in m.t:
            try:
                m.M[t].setub(cap_M)
                if m.M[t].value is not None and m.M[t].value > cap_M:
                    m.M[t].value = cap_M
            except Exception:
                continue
    if floor_C is not None and hasattr(m, 'C'):
        for (t,j) in list(m.C.index_set()):  # type: ignore
            try:
                m.C[t,j].setlb(floor_C)
                if m.C[t,j].value is not None and m.C[t,j].value < floor_C:
                    m.C[t,j].value = floor_C
            except Exception:
                continue

    # Warm-start strategy: solve a 1-element tiny model, map last state back as initial guesses
    if warmstart:
        try:
            m_ws = build_fn(total_sim_time=total_sim_time,
                            discretization='collocation',
                            n_f_elements_t=1,
                            total_f_elements_t=1)
            # light regularization mirroring settings
            if regularize and hasattr(m_ws, 'C'):
                for (t,j) in list(m_ws.C.index_set()):
                    if m_ws.C[t,j].value == 0:
                        m_ws.C[t,j].value = epsilon
            opt_ws_name = pick_available_solver(return_options=False)
            pe.SolverFactory(opt_ws_name).solve(m_ws, tee=False)
            # propagate last state
            if hasattr(m, 'C') and hasattr(m_ws, 'C'):
                t_last_ws = m_ws.t.last()
                for (t,j) in list(m.C.index_set()):  # type: ignore
                    try:
                        val = pe.value(m_ws.C[t_last_ws,j])
                        if val is not None:
                            m.C[t,j].value = val
                    except Exception:
                        continue
            if hasattr(m, 'M') and hasattr(m_ws, 'M'):
                valM = pe.value(m_ws.M[m_ws.t.last()])
                if valM is not None:
                    for t in m.t:
                        try:
                            m.M[t].value = valM
                        except Exception:
                            pass
        except Exception:
            # Warm-start failure is non-fatal; continue
            pass

    # Optional mass balance slack (Diff_mass only) – deactivates original constraint
    if add_mass_slack and hasattr(m, 'Diff_mass'):
        try:
            m.Diff_mass.deactivate()
            m.slack_mass = pe.Var(m.t, within=pe.Reals, initialize=0)
            def _Diff_mass_relaxed(mdl, t):
                if t == mdl.t.first() and mdl.current_starting_time == 0:
                    return mdl.M[t] == mdl.M0
                elif t == mdl.t.first():
                    return mdl.M[t] == mdl.M0_prev
                else:
                    return mdl.dMdt[t] == mdl.final_time * (mdl.Fin[t]) + mdl.slack_mass[t]
            m.Diff_mass_relaxed = pe.Constraint(m.t, rule=_Diff_mass_relaxed)
            # Replace objective with penalized version
            if hasattr(m, 'obj'):
                try:
                    base_expr = m.obj.expr
                    m.obj.deactivate()
                    m.obj_relaxed = pe.Objective(expr=base_expr + slack_weight * sum(m.slack_mass[t]**2 for t in m.t if t != m.t.first()))
                except Exception:
                    pass
        except Exception:
            pass

    # Initial-only mass balance slack (C1) if requested and not already using full mass slack
    if initial_mass_slack and not add_mass_slack and hasattr(m, 'Diff_mass'):
        try:
            # Keep original constraints active except we replace the first point equation
            # Strategy: deactivate Diff_mass at t=first, add slack var and new constraint
            t0 = m.t.first()
            # Identify index form of Diff_mass
            try:
                m.Diff_mass[t0].deactivate()
            except Exception:
                pass
            m.slack_mass0 = pe.Var(initialize=0, within=pe.Reals)
            def _Diff_mass_initial_relaxed(mdl):
                # Original forms: if starting_time==0 => M[t0]==M0 else M[t0]==M0_prev
                if mdl.current_starting_time == 0:
                    return mdl.M[t0] == mdl.M0 + mdl.slack_mass0
                else:
                    return mdl.M[t0] == mdl.M0_prev + mdl.slack_mass0
            m.Diff_mass_initial_relaxed = pe.Constraint(rule=_Diff_mass_initial_relaxed)
            if hasattr(m, 'obj'):
                try:
                    base_expr = m.obj.expr
                    m.obj.deactivate()
                    m.obj_initial_relaxed = pe.Objective(expr=base_expr + initial_slack_weight * (m.slack_mass0**2))
                except Exception:
                    pass
        except Exception:
            pass

    # Align modular initial conditions (placeholder: could load from baseline; here we mimic stabilized modular defaults)
    if align_modular_init:
        try:
            # If M has a middle-range value, set all initial guesses to ~1000
            if hasattr(m, 'M'):
                for t in m.t:
                    if m.M[t].value is not None and m.M[t].value < 100:
                        m.M[t].value = 1000
            if hasattr(m, 'C'):
                for (t,j) in list(m.C.index_set()):
                    if m.C[t,j].value is None or m.C[t,j].value < 1e-6:
                        # Use tiny but non-zero seed; for ethanol mimic modular ~6 g/kg final guess
                        seed = 6.0 if j == 'Eth' else 0.001
                        m.C[t,j].value = seed
        except Exception:
            pass

    # Feed alignment: handle both indexed (time-dependent) and scalar feed flow variables
    if feed_align and hasattr(m, 'Feed_constraint') and hasattr(m, 'Fin') and hasattr(m, 'F_C5liquid') and hasattr(m, 'F_liquified_fibers'):
        try:
            m.Feed_constraint.deactivate()

            # Helper to extract (possibly scalar) feed component for a given time t
            def _at(var, t):
                try:
                    # Indexed var (has dim() > 0 and supports __getitem__)
                    if getattr(var, 'dim', lambda: 0)() > 0:
                        return var[t]
                except Exception:
                    pass
                # Scalar Var: return itself
                return var

            def _Feed_align(mdl, t):
                base_val = 0
                if hasattr(mdl, 'F_base'):
                    try:
                        base_val = _at(mdl.F_base, t)
                    except Exception:
                        base_val = 0
                acid_val = 0
                if hasattr(mdl, 'F_acid'):
                    try:
                        acid_val = _at(mdl.F_acid, t)
                    except Exception:
                        acid_val = 0
                return mdl.Fin[t] == _at(mdl.F_liquified_fibers, t) + _at(mdl.F_C5liquid, t) + base_val + acid_val
            m.Feed_constraint_aligned = pe.Constraint(m.t, rule=_Feed_align)
        except Exception:
            pass

    # Feed slack (post-alignment or original): add slack term per t (also scalar-safe)
    if feed_slack and hasattr(m, 'Fin') and (hasattr(m, 'Feed_constraint_aligned') or hasattr(m, 'Feed_constraint')):
        try:
            # Choose active constraint reference
            c_ref = getattr(m, 'Feed_constraint_aligned', None)
            if c_ref is None or not getattr(c_ref, 'active', False):
                c_ref = getattr(m, 'Feed_constraint', None)
            if c_ref is not None and getattr(c_ref, 'active', False):
                c_ref.deactivate()
            m.feed_slack = pe.Var(m.t, within=pe.Reals, initialize=0)

            def _at(var, t):
                try:
                    if getattr(var, 'dim', lambda: 0)() > 0:
                        return var[t]
                except Exception:
                    pass
                return var

            def _Feed_slack_rule(mdl, t):
                return mdl.Fin[t] == _at(mdl.F_liquified_fibers, t) + _at(mdl.F_C5liquid, t) + mdl.feed_slack[t]
            m.Feed_constraint_slack = pe.Constraint(m.t, rule=_Feed_slack_rule)
        except Exception:
            pass

    # Simple feed mode: deactivate any feed constraints and impose Fin pattern (e.g., zero after t0)
    if simple_feed and hasattr(m, 'Fin'):
        try:
            # Deactivate any existing feed constraints
            for cname in ('Feed_constraint_slack','Feed_constraint_aligned','Feed_constraint'):
                comp = getattr(m, cname, None)
                if comp is not None:
                    try:
                        comp.deactivate()
                    except Exception:
                        pass
            # Zero constituent feeds if present
            for vname in ('F_liquified_fibers','F_C5liquid','F_base','F_acid'):
                if hasattr(m, vname):
                    var = getattr(m, vname)
                    try:
                        if getattr(var,'dim',lambda:0)() > 0:
                            for t in m.t:
                                var[t].fix(0)
                        else:
                            var.fix(0)
                    except Exception:
                        pass
            # Determine target feed value (default 0)
            feed_val = 0.0 if simple_feed_rate is None else simple_feed_rate
            for t in m.t:
                try:
                    m.Fin[t].fix(feed_val)
                except Exception:
                    pass
        except Exception:
            pass

    # Normalized feed: reconstruct original 3-phase logic using tau in [0,1]
    if normalized_feed and hasattr(m, 'Fin') and hasattr(m, 't'):
        try:
            # Deactivate any original feed constraints if present
            for cname in ('Feed_constraint_slack','Feed_constraint_aligned','Feed_constraint'):
                comp = getattr(m, cname, None)
                if comp is not None:
                    try:
                        comp.deactivate()
                    except Exception:
                        pass
            # Ensure constituent flows exist; if scalar create small indexed surrogates
            # We only need them for expression placeholders; keep current values.
            t0 = m.t.first()
            t_last = m.t.last()
            # Pre-compute denominators
            denom = float(pe.value(m.final_time)) if hasattr(m, 'final_time') else 1.0
            # Relative cutoffs
            c1 = 10.0/190.0
            c2 = 70.0/190.0

            def _at(var, t):
                try:
                    if getattr(var, 'dim', lambda: 0)() > 0:
                        return var[t]
                except Exception:
                    pass
                return var

            # Rule: set Fin = patterns of F_liquified_fibers (Liq) and F_C5liquid (C5)
            # Optional scaling factor based on horizon (total_sim_time / (190h))
            scale_fac = 1.0
            try:
                if normalized_feed_scale:
                    # total_sim_time passed into build_fn -> accessible through final_time if consistent units (seconds)
                    # original 190h in seconds:
                    orig = 190.0*3600.0
                    if hasattr(m, 'final_time'):
                        ft = float(pe.value(m.final_time))
                        # final_time in legacy seems to be total_sim_time (seconds)
                        scale_fac = ft / orig if orig > 0 else 1.0
            except Exception:
                scale_fac = 1.0

            def _scaled(var, t):
                base = _at(var, t)
                try:
                    return scale_fac * base
                except Exception:
                    return base

            def _Feed_norm(mdl, t):
                # Compute normalized tau using actual closing time
                # original code: current_starting_time + t*(current_final_time - current_starting_time)
                # We'll approximate by scaling t in [0,1] directly since transformation already normalized t domain.
                tau = float(pe.value(t))  # t in [0,1]
                # Phase logic by tau relative cutoffs
                if tau <= c1:
                    # inoculum phase: only liquified fibers
                    return mdl.Fin[t] == _scaled(mdl.F_liquified_fibers, t)
                elif tau <= c2:
                    return mdl.Fin[t] == _scaled(mdl.F_liquified_fibers, t) + _scaled(mdl.F_C5liquid, t) + ( _scaled(mdl.F_base, t) if hasattr(mdl,'F_base') else 0) + (_scaled(mdl.F_acid, t) if hasattr(mdl,'F_acid') else 0)
                else:
                    return mdl.Fin[t] == 0
            m.Feed_constraint_normalized = pe.Constraint(m.t, rule=_Feed_norm)
        except Exception:
            pass

    # Sync Fin initial guesses to normalized feed expression if requested (after building constraint)
    if sync_fin_initial and hasattr(m, 'Feed_constraint_normalized') and hasattr(m, 'Fin'):
        try:
            for t in m.t:
                c = m.Feed_constraint_normalized[t]
                # body: Fin[t] == expr  -> we extract RHS by substituting Fin[t] with current value
                # Simpler: evaluate (rhs) by solving for Fin[t] from expression: expr_body - Fin[t] == 0
                # here c.body is Fin[t] - RHS == 0 or Fin[t] == RHS depending on construction
                # We reconstruct RHS: if c.body is an Equality (Var == expr) Pyomo stores directly; easiest is value of Fin currently or re-evaluate flows
                # We'll recompute using same rule logic rather than parse expression.
                # Reuse _Feed_norm logic via temporary evaluation:
                # Not trivial to call rule; fallback: approximate by summing flows under same phase logic
                # We'll mimic the rule quickly:
                tau = float(pe.value(t))
                c1 = 10.0/190.0
                c2 = 70.0/190.0
                def _at(var, tt):
                    try:
                        if getattr(var,'dim',lambda:0)() > 0:
                            return var[tt]
                    except Exception:
                        pass
                    return var
                scale_fac = 1.0
                if normalized_feed_scale and hasattr(m,'final_time'):
                    orig = 190.0*3600.0
                    try:
                        ft = float(pe.value(m.final_time))
                        scale_fac = ft/orig if orig>0 else 1.0
                    except Exception:
                        pass
                def _scaled(var, tt):
                    base = _at(var, tt)
                    return scale_fac*base
                if tau <= c1:
                    rhs = pe.value(_scaled(m.F_liquified_fibers, t)) if hasattr(m,'F_liquified_fibers') else 0.0
                elif tau <= c2:
                    rhs = 0.0
                    if hasattr(m,'F_liquified_fibers'): rhs += pe.value(_scaled(m.F_liquified_fibers, t))
                    if hasattr(m,'F_C5liquid'): rhs += pe.value(_scaled(m.F_C5liquid, t))
                    if hasattr(m,'F_base'): rhs += pe.value(_scaled(m.F_base, t))
                    if hasattr(m,'F_acid'): rhs += pe.value(_scaled(m.F_acid, t))
                else:
                    rhs = 0.0
                try:
                    m.Fin[t].value = rhs
                except Exception:
                    pass
        except Exception:
            pass

    # Add slack to normalized feed if requested
    if normalized_feed_slack and hasattr(m, 'Feed_constraint_normalized'):
        try:
            m.Feed_constraint_normalized.deactivate()
            m.feed_norm_slack = pe.Var(m.t, initialize=0.0, within=pe.Reals)
            # Rebuild expression (reuse logic used earlier, condensed):
            c1 = 10.0/190.0
            c2 = 70.0/190.0
            def _at(var, t):
                try:
                    if getattr(var,'dim',lambda:0)() > 0:
                        return var[t]
                except Exception:
                    pass
                return var
            scale_fac = 1.0
            if normalized_feed_scale and hasattr(m,'final_time'):
                orig = 190.0*3600.0
                try:
                    ft = float(pe.value(m.final_time))
                    scale_fac = ft/orig if orig>0 else 1.0
                except Exception:
                    pass
            def _scaled(var, t):
                base = _at(var, t)
                return scale_fac*base
            def _Feed_norm_slack(mdl, t):
                tau = float(pe.value(t))
                if tau <= c1:
                    rhs = _scaled(mdl.F_liquified_fibers, t) if hasattr(mdl,'F_liquified_fibers') else 0
                elif tau <= c2:
                    rhs = 0
                    if hasattr(mdl,'F_liquified_fibers'): rhs += _scaled(mdl.F_liquified_fibers, t)
                    if hasattr(mdl,'F_C5liquid'): rhs += _scaled(mdl.F_C5liquid, t)
                    if hasattr(mdl,'F_base'): rhs += _scaled(mdl.F_base, t)
                    if hasattr(mdl,'F_acid'): rhs += _scaled(mdl.F_acid, t)
                else:
                    rhs = 0
                return mdl.Fin[t] == rhs + mdl.feed_norm_slack[t]
            m.Feed_constraint_normalized_relaxed = pe.Constraint(m.t, rule=_Feed_norm_slack)
            # Augment objective
            if hasattr(m,'obj'):
                try:
                    base_expr = m.obj.expr
                    m.obj.deactivate()
                    m.obj_norm_slack = pe.Objective(expr= base_expr + normalized_feed_slack_weight*sum(m.feed_norm_slack[t]**2 for t in m.t))
                except Exception:
                    pass
        except Exception:
            pass

    # Micro slack puntual: aggregate budgeted absolute deviation (mutually exclusive with distributed slack)
    if (not normalized_feed_slack) and normalized_feed_micro_slack and hasattr(m, 'Feed_constraint_normalized'):
        try:
            m.Feed_constraint_normalized.deactivate()
            m.feed_norm_slack_pos = pe.Var(m.t, initialize=0.0, within=pe.NonNegativeReals)
            m.feed_norm_slack_neg = pe.Var(m.t, initialize=0.0, within=pe.NonNegativeReals)
            m.feed_norm_slack_budget_con = pe.Constraint(expr=sum(m.feed_norm_slack_pos[t] + m.feed_norm_slack_neg[t] for t in m.t) <= normalized_feed_micro_slack_budget)
            c1 = 10.0/190.0
            c2 = 70.0/190.0
            def _at(var, t):
                try:
                    if getattr(var,'dim',lambda:0)() > 0:
                        return var[t]
                except Exception:
                    pass
                return var
            scale_fac = 1.0
            if normalized_feed_scale and hasattr(m,'final_time'):
                orig = 190.0*3600.0
                try:
                    ft = float(pe.value(m.final_time))
                    scale_fac = ft/orig if orig>0 else 1.0
                except Exception:
                    pass
            def _scaled(var, t):
                base = _at(var, t)
                return scale_fac*base
            def _Feed_norm_micro(mdl, t):
                tau = float(pe.value(t))
                if tau <= c1:
                    rhs = _scaled(mdl.F_liquified_fibers, t) if hasattr(mdl,'F_liquified_fibers') else 0
                elif tau <= c2:
                    rhs = 0
                    if hasattr(mdl,'F_liquified_fibers'): rhs += _scaled(mdl.F_liquified_fibers, t)
                    if hasattr(mdl,'F_C5liquid'): rhs += _scaled(mdl.F_C5liquid, t)
                    if hasattr(mdl,'F_base'): rhs += _scaled(mdl.F_base, t)
                    if hasattr(mdl,'F_acid'): rhs += _scaled(mdl.F_acid, t)
                else:
                    rhs = 0
                return mdl.Fin[t] == rhs + mdl.feed_norm_slack_pos[t] - mdl.feed_norm_slack_neg[t]
            m.Feed_constraint_normalized_micro = pe.Constraint(m.t, rule=_Feed_norm_micro)
            if hasattr(m,'obj'):
                try:
                    base_expr = m.obj.expr
                    m.obj.deactivate()
                    quad_pen = sum((m.feed_norm_slack_pos[t] + m.feed_norm_slack_neg[t])**2 for t in m.t)
                    m.obj_norm_micro_slack = pe.Objective(expr= base_expr + normalized_feed_micro_slack_weight*quad_pen)
                except Exception:
                    pass
        except Exception:
            pass

    # Objective augmentation for smoothing Fin(t) and feed_slack penalty (if needed)
    if (smooth_fin_weight > 0 or (feed_slack and feed_slack_weight > 0)) and hasattr(m, 'obj'):
        try:
            base_expr = m.obj.expr
            m.obj.deactivate()
            fin_smooth = 0
            if smooth_fin_weight > 0:
                try:
                    fin_smooth = sum((m.Fin[t] - m.Fin[m.t.prev(t)])**2 for t in m.t if t != m.t.first())
                except Exception:
                    fin_smooth = 0
            feed_slack_pen = 0
            if feed_slack and feed_slack_weight > 0 and hasattr(m, 'feed_slack'):
                feed_slack_pen = sum(m.feed_slack[t]**2 for t in m.t)
            m.obj_aug = pe.Objective(expr=base_expr + smooth_fin_weight*fin_smooth + feed_slack_weight*feed_slack_pen)
        except Exception:
            pass

    # Optional scaling: create a ScaleSuffix if not present and set nominal scaling

    # Jitter concentrations at interior time points to break degeneracy if requested
    if jitter_conc and hasattr(m, 'C') and hasattr(m, 't'):
        try:
            import random
            if jitter_seed is not None:
                random.seed(int(jitter_seed))
            t_first = m.t.first()
            t_last = m.t.last()
            for (t,j) in list(m.C.index_set()):  # type: ignore
                # Skip endpoints to preserve initial/final conditions
                if t == t_first or t == t_last:
                    continue
                try:
                    base = m.C[t,j].value
                    if base is None:
                        continue
                    perturb = (2*random.random()-1) * jitter_conc_mag * max(abs(base), 1.0)
                    m.C[t,j].value = base + perturb
                except Exception:
                    continue
        except Exception:
            pass
    if scale_model:
        try:
            from pyomo.environ import Suffix
            if not hasattr(m, 'scaling_factor'):  # Avoid double creation
                m.scaling_factor = Suffix(direction=Suffix.EXPORT)
            if hasattr(m, 'C'):
                for (t,j) in list(m.C.index_set()):
                    m.scaling_factor[m.C[t,j]] = 0.1  # assume typical magnitude ~10
            if hasattr(m, 'M'):
                for t in m.t:
                    m.scaling_factor[m.M[t]] = 1e-3  # M ~1000
            # Scale Diff_comp constraints to tame huge residual factors (use inverse of final_time if available)
            if 'Diff_comp' in m.component_map():
                try:
                    ft_val = float(pe.value(m.final_time)) if hasattr(m,'final_time') else 1.0
                except Exception:
                    ft_val = 1.0
                base_factor = 1.0 / max(ft_val,1.0)
                # Keep factor within a reasonable range
                if base_factor < 1e-6:
                    base_factor = 1e-6
                if base_factor > 1e-2:
                    base_factor = 1e-2
                try:
                    for cdata in m.Diff_comp.values():  # type: ignore
                        m.scaling_factor[cdata] = base_factor
                except Exception:
                    pass
        except Exception:
            pass

    # Relax initial component dynamic constraints: replace Diff_comp[t0,*] with direct algebraic initial conditions
    if relax_initial_comp and 'Diff_comp' in m.component_map() and hasattr(m, 't') and hasattr(m, 'C'):
        try:
            t0 = m.t.first()
            # Deactivate each Diff_comp[t0, j]
            # Diff_comp appears to be indexed by (t,j); try structured access
            for key, c in list(m.Diff_comp.items()):  # type: ignore
                try:
                    if isinstance(key, tuple) and key[0] == t0:
                        c.deactivate()
                except Exception:
                    continue
            # Build replacement constraints
            def _Initial_comp_rule(mdl, j):
                # Determine reference initial value
                if mdl.current_starting_time == 0 and hasattr(mdl, 'C0'):
                    ref = pe.value(mdl.C0[j])
                elif hasattr(mdl, 'C0_prev'):
                    ref = pe.value(mdl.C0_prev[j])
                else:
                    return pe.Constraint.Skip
                # Clip to variable lower bound (floor_C) if reference below it to avoid infeasible equality
                var = mdl.C[t0, j]
                try:
                    lb = var.lb
                except Exception:
                    lb = None
                if lb is not None and ref < lb:
                    ref = lb
                return var == ref
            if hasattr(m, 'j'):
                m.Diff_comp_initial_relaxed = pe.Constraint(m.j, rule=_Initial_comp_rule)
        except Exception:
            pass

    # Pick solver
    if solver is None:
        try:
            solver = pick_available_solver(return_options=False)
        except Exception as e:
            return {"status": "no_solver", "error": str(e)}

    opt = pe.SolverFactory(solver)
    # Apply Ipopt options if available and using ipopt
    if solver and 'ipopt' in solver.lower():
        if ipopt_max_iter is not None:
            opt.options['max_iter'] = int(ipopt_max_iter)
        if ipopt_tol is not None:
            opt.options['tol'] = float(ipopt_tol)
        if ipopt_acceptable_tol is not None:
            opt.options['acceptable_tol'] = float(ipopt_acceptable_tol)
        if ipopt_print_level is not None:
            opt.options['print_level'] = int(ipopt_print_level)
        if ipopt_linear_solver is not None:
            opt.options['linear_solver'] = str(ipopt_linear_solver)
        if ipopt_bound_relax_factor is not None:
            opt.options['bound_relax_factor'] = float(ipopt_bound_relax_factor)
        if ipopt_constr_viol_tol is not None:
            opt.options['constr_viol_tol'] = float(ipopt_constr_viol_tol)
    if not opt.available(False):
        return {"status": "solver_unavailable", "solver_name": solver}

    try:
        res = opt.solve(m, tee=tee)
        rc = str(res.solver.termination_condition)
        stat = str(res.solver.status)
    except Exception as e:  # capture solver failure
        rc = 'exception'
        stat = e.__class__.__name__

    try:
        final_eth = pe.value(m.C[m.t.last(), 'Eth']) if ('C' in m.component_map() and ('Eth' in list(m.j))) else None
    except Exception:
        final_eth = None
    try:
        final_M = pe.value(m.M[m.t.last()]) if 'M' in m.component_map() else None
    except Exception:
        final_M = None
    try:
        objv = pe.value(m.obj) if 'obj' in m.component_map() else None
    except Exception:
        objv = None

    # Size metrics
    try:
        n_vars = sum(1 for _ in m.component_data_objects(pe.Var, active=True))
        n_cons = sum(1 for _ in m.component_data_objects(pe.Constraint, active=True))
    except Exception:
        n_vars = n_cons = None

    # Capture micro slack aggregate usage if present
    micro_slack_usage = None
    if 'feed_norm_slack_pos' in m.component_map() and 'feed_norm_slack_neg' in m.component_map():
        try:
            micro_slack_usage = sum(pe.value(m.feed_norm_slack_pos[t] + m.feed_norm_slack_neg[t]) for t in m.t)
        except Exception:
            micro_slack_usage = None

    diag = None
    if diagnostics:
        residuals = []
        try:
            for c in m.component_data_objects(pe.Constraint, active=True):
                if (c.body is not None) and (c.has_lb() or c.has_ub()):
                    try:
                        val = pe.value(c.body)
                    except Exception:
                        continue
                    lb = c.lower if c.has_lb() else None
                    ub = c.upper if c.has_ub() else None
                    viol = 0.0
                    if lb is not None and val < lb:
                        viol = lb - val
                    if ub is not None and val > ub:
                        viol = max(viol, val - ub)
                    if viol > 0:
                        residuals.append((viol, c.name))
            residuals.sort(reverse=True, key=lambda x: x[0])
            diag = [{"violation": v, "constraint": n} for v, n in residuals[:diagnostics_top]]
        except Exception:
            diag = None

    return {
        "status": "ok" if rc in ("optimal", "locallyOptimal") else "not_optimal",
        "solver_status": stat,
        "termination_condition": rc,
        "final_ethanol_conc": final_eth,
        "final_hold_up": final_M,
        "objective": objv,
        "solver_name": solver,
        "nfe": n_f_elements_t,
        "regularized": regularize,
        "floor_M": floor_M,
        "floor_C": floor_C,
        "warmstart": warmstart,
        "mass_slack": add_mass_slack,
    "initial_mass_slack": initial_mass_slack,
        "cap_M": cap_M,
        "n_vars": n_vars,
        "n_cons": n_cons,
        "diagnostics": diag,
        "feed_align": feed_align,
        "feed_slack": feed_slack,
        "smooth_fin_weight": smooth_fin_weight,
        "align_modular_init": align_modular_init,
        "scale_model": scale_model,
        "simple_feed": simple_feed,
        "simple_feed_rate": simple_feed_rate,
        "normalized_feed": normalized_feed,
        "normalized_feed_scale": normalized_feed_scale,
        "ipopt_max_iter": ipopt_max_iter,
        "ipopt_tol": ipopt_tol,
        "ipopt_acceptable_tol": ipopt_acceptable_tol,
        "ipopt_print_level": ipopt_print_level,
    "ipopt_linear_solver": ipopt_linear_solver,
    "ipopt_bound_relax_factor": ipopt_bound_relax_factor,
    "ipopt_constr_viol_tol": ipopt_constr_viol_tol,
        "normalized_feed_slack": normalized_feed_slack,
        "normalized_feed_slack_weight": normalized_feed_slack_weight,
        "normalized_feed_micro_slack": normalized_feed_micro_slack,
        "normalized_feed_micro_slack_budget": normalized_feed_micro_slack_budget,
        "normalized_feed_micro_slack_weight": normalized_feed_micro_slack_weight,
        "normalized_feed_micro_slack_usage": micro_slack_usage,
        "sync_fin_initial": sync_fin_initial,
        "jitter_conc": jitter_conc,
        "jitter_conc_mag": jitter_conc_mag,
        "jitter_seed": jitter_seed,
        "relax_initial_comp": relax_initial_comp,
    }

if __name__ == "__main__":  # quick manual test
    out = run_legacy_single_step(n_f_elements_t=1)
    print(json.dumps(out, indent=2))
