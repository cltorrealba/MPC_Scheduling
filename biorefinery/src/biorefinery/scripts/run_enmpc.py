"""ENMPC loop runner with advanced features.

Enhancements:
- Receding horizon NMPC with per-step application.
- Economic objective (surrogate or exact symbolic) optional.
- Disturbances: feed (design-time) and execution (runtime drift) with drift metrics.
- Warm start via last applied control values.
- Recording of predicted vs realized end state each iteration.
- Periodic checkpoint JSON writes (uncompressed) and resume capability.
- Optional trajectory compression to step endpoints only after completion.
"""
from __future__ import annotations
import json, argparse, random, math, os
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model
from biorefinery.feeds.profile import apply_feed_profile, DEFAULT_PHASES
from biorefinery.metrics import compute_economic_metric
from biorefinery.optimization.solvers import pick_available_solver
import hashlib
import subprocess


def _pick_solver(force_name: str | None):
    if force_name:
        return force_name
    name, _ = pick_available_solver(return_options=True)
    if name is None:
        raise RuntimeError("No solver available for ENMPC run")
    return name


def _build_model(args, current_start_s: float, init_conc: dict, init_hold_up: float):
    # IMPORTANT: For NMPC we want the model prediction horizon to match horizon_time_h, not total_time_h.
    # The original builder scales final_time = (n_f_elements_t/total_f_elements_t)*total_sim_time.
    # To force final_time == horizon_time_s we pass total_f_elements_t = nfe and total_sim_time = horizon_time.
    horizon_time_s = args.horizon_time_h * 3600.0
    m = build_fermentation_model(
        n_f_elements_t=args.nfe,
        total_f_elements_t=args.nfe,  # ensures final_time = horizon_time_s
        total_sim_time=horizon_time_s,
        current_start_time_seconds=current_start_s,
        include_kinetics=True,
        detailed_kinetics=args.detailed,
        initial_concentrations=init_conc,
        enable_mass_balance=True,
        feed_control=False,
        max_concentration=getattr(args,'max_concentration',200.0),
        min_hold_up=getattr(args,'min_hold_up',100.0),
        rate_scale=getattr(args,'rate_scale',1.0),
    )
    # Optional monotonic hold-up (non-decreasing) to avoid spurious solver-induced drops
    if getattr(args,'enforce_monotonic_m', False) and hasattr(m,'M'):
        try:
            m.monotonic_M = pe.ConstraintList()
            prev = None
            for tau in m.t:
                if prev is not None:
                    # allow tiny numerical decrease tolerance
                    m.monotonic_M.add(m.M[tau] >= m.M[prev] - 1e-9)
                prev = tau
        except Exception:
            pass
    if hasattr(m, 'M0'):
        m.M0.set_value(init_hold_up)
    first_t = m.t.first()
    if current_start_s > 0:
        for sp, val in init_conc.items():
            if sp in m.j:
                m.C[first_t, sp].fix(val)
        m.M[first_t].fix(init_hold_up)
    return m


def _apply_objective(m, economic: bool, exact: bool):
    # Remove existing objective to avoid replacement warning
    if hasattr(m, 'obj'):
        try:
            m.del_component(m.obj)
        except Exception:
            pass
    tL = m.t.last()
    if economic and exact:
        cell0 = m.C[m.t.first(), 'Cell']
        m.obj = pe.Objective(expr=-(50.0 * cell0 - 5.0 * m.C[tL, 'Eth'] * m.M[tL]), sense=pe.minimize)
    elif economic:
        m.obj = pe.Objective(expr=5.0 * m.C[tL, 'Eth'] * m.M[tL], sense=pe.minimize)
    else:
        m.obj = pe.Objective(expr=m.C[tL, 'Eth'], sense=pe.maximize)


def _extract_applied_control(m):
    tau0 = m.t.first()
    return {
        'F_liquified_fibers': float(pe.value(m.F_liquified_fibers[tau0])),
        'F_C5liquid': float(pe.value(m.F_C5liquid[tau0])),
    }


def _disturb_feed(base: dict[str, float], alpha: float):
    if alpha <= 0:
        return base
    return {k: v * (1.0 + random.uniform(-alpha, alpha)) for k, v in base.items()}


def _write_json_atomic(path: str, payload: dict):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def _config_hash(args):
    keys = ['total_time_h','step_time_h','horizon_time_h','nfe','total_elements',
            'economic_objective','economic_objective_exact','disturbance_alpha',
        'execution_disturbance_alpha','export_step_only','seed','no_rates','force_nonzero_drift','drift_exclude_holdup',
            'constant_hold_up','mass_balance_slack','mass_balance_slack_weight',
            'max_concentration','min_hold_up','rate_scale','enforce_monotonic_m']
    payload = {k: getattr(args, k, None) for k in keys}
    raw = json.dumps(payload, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _git_commit_short():
    try:
        out = subprocess.check_output(['git','rev-parse','--short','HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
        return out or None
    except Exception:
        return None


def _encode_index(idx):
    if not isinstance(idx, tuple):
        idx = (idx,)
    enc = []
    for it in idx:
        if isinstance(it, float):
            enc.append(str(round(it, 6)))
        else:
            enc.append(str(it))
    return '|'.join(enc)


def _capture_primal_solution(m):
    """Capture primal values of key variables for warm starting next horizon.

    Sanitization rules:
      * Very small negatives on NonNegative vars (>-1e-8) -> clamped to 0.0
      * Larger negatives on NonNegative vars are skipped (not stored).
    This avoids Pyomo W1001 warnings when re-injecting solver numerical noise.
    """
    target_names = {'C', 'M', 'F_C5liquid', 'F_liquified_fibers', 'q', 'R'}
    data = {}
    for comp in m.component_objects(pe.Var, descend_into=True):
        name = comp.getname().split('.')[-1]
        if name not in target_names:
            continue
        slot = {}
        try:
            for idx in comp:
                var = comp[idx]
                val = var.value
                if val is None:
                    continue
                # Domain-based simple heuristic
                lb = None
                try:
                    lb = var.lb
                except Exception:
                    lb = None
                if lb is not None and lb >= 0 and val < 0:
                    if val > -1e-8:
                        val = 0.0
                    else:
                        # Skip storing large negative inconsistent with domain
                        continue
                slot[_encode_index(idx)] = float(val)
        except Exception:
            continue
        if slot:
            data[name] = slot
    return data


def _apply_warm_start(m, snapshot):
    applied_any = False
    if not snapshot:
        return applied_any
    for comp in m.component_objects(pe.Var, descend_into=True):
        name = comp.getname().split('.')[-1]
        snap = snapshot.get(name)
        if not snap:
            continue
        try:
            for idx in comp:
                var = comp[idx]
                if var.fixed:
                    continue
                key = _encode_index(idx)
                if key in snap:
                    val = snap[key]
                    # Re-apply same sanitization guard
                    lb = None
                    try:
                        lb = var.lb
                    except Exception:
                        lb = None
                    if lb is not None and lb >= 0 and val < 0:
                        if val > -1e-8:
                            val = 0.0
                        else:
                            continue
                    var.set_value(val)
                    applied_any = True
        except Exception:
            continue
    return applied_any


def run_enmpc(args):
    solver_name = None if args.constant_policy else _pick_solver(args.solver)
    total_time_s = args.total_time_h * 3600.0
    step_s = args.step_time_h * 3600.0
    horizon_s = args.horizon_time_h * 3600.0
    if horizon_s < step_s:
        raise ValueError("Horizon must be >= step time")
    n_iters = int(math.ceil(total_time_s / step_s))
    if args.seed is not None:
        random.seed(args.seed)

    init_conc = {'G':10.0,'X':5.0,'Eth':0.0,'Cell':1.0,'F':0.2,'HMF':0.1,'ACT':0.05,'CO2':0.0}
    init_hold_up = 1000.0
    feed_comp_base = {sp: 0.0 for sp in init_conc.keys()}
    records = []
    trajectory_time = []
    trajectory_species = {sp: [] for sp in init_conc.keys()}
    trajectory_M = []
    control_series_F_liqfib = []  # full-horizon capture each step
    control_series_F_C5 = []
    trajectory_q = None
    trajectory_R = None
    current_time_s = 0.0
    last_applied_control = None
    prev_solution_snapshot = None
    warm_start_applied_count = 0

    # Resume
    if args.resume_from:
        if not os.path.exists(args.resume_from):
            raise FileNotFoundError(args.resume_from)
        with open(args.resume_from, 'r', encoding='utf-8') as f:
            prev = json.load(f)
        meta_prev = prev.get('meta', {})
        if meta_prev.get('export_step_only'):
            raise ValueError("Cannot resume from compressed export_step_only run")
        prev_hash = meta_prev.get('config_hash')
        current_hash = _config_hash(args)
        if prev_hash and prev_hash != current_hash and not getattr(args,'ignore_config_hash',False):
            raise ValueError(f"Configuration hash mismatch: prev={prev_hash} current={current_hash}. Use --ignore-config-hash to override.")
        # Optional param_hash guard (only if both present and --hash-params requested now)
        prev_param_hash = meta_prev.get('param_hash')
        # Only enforce if previous run stored param_hash AND current user wants param hashing
        if getattr(args,'hash_params', False) and prev_param_hash and not getattr(args,'ignore_param_hash', False):
            # Build a tiny temp model to compute current param hash
            try:
                from biorefinery.models.api_contract import FermentationConfig, build_fermentation_model_v2
                cfg_tmp = FermentationConfig(horizon_h=args.horizon_time_h, nfe=args.nfe,
                                             include_kinetics=True, detailed_kinetics=args.detailed,
                                             enable_mass_balance=True)
                tmp_res = build_fermentation_model_v2(cfg_tmp)
                current_param_hash = tmp_res.param_hash
            except Exception:
                current_param_hash = None
            if current_param_hash and current_param_hash != prev_param_hash:
                raise ValueError(f"Parameter hash mismatch: prev={prev_param_hash} current={current_param_hash}. Use --ignore-param-hash to override.")
        records = prev.get('records', [])
        traj = prev.get('trajectory', {})
        trajectory_time = traj.get('time_s', [])
        for sp in trajectory_species.keys():
            trajectory_species[sp] = traj.get('species', {}).get(sp, [])
        trajectory_M = traj.get('hold_up', [])
        if 'q_series' in traj:
            trajectory_q = traj['q_series']
        if 'R_series' in traj:
            trajectory_R = traj['R_series']
        if records:
            current_time_s = records[-1]['t_end_s']
            realized = records[-1].get('realized_end_state') or {}
            C_last = realized.get('C') or {}
            M_last = realized.get('M')
            if M_last is not None:
                init_hold_up = M_last
            for sp in init_conc.keys():
                if sp in C_last:
                    init_conc[sp] = C_last[sp]
            last_applied_control = records[-1].get('applied_control')

    start_idx = len(records)
    max_new = args.max_iterations if args.max_iterations is not None else n_iters

    # Prepare results directory
    if getattr(args,'results_dir', None):
        os.makedirs(args.results_dir, exist_ok=True)
        if args.output and not os.path.isabs(args.output):
            args.output = os.path.join(args.results_dir, args.output)
        if args.resume_from and not os.path.isabs(args.resume_from):
            args.resume_from = os.path.join(args.results_dir, args.resume_from)

    for k in range(start_idx, n_iters):
        if (k - start_idx) >= max_new:
            break
        m = _build_model(args, current_time_s, init_conc, init_hold_up)
        apply_feed_profile(m, DEFAULT_PHASES, override_existing=True)
        # (1) Zero-fix of q/R at initial time to avoid large unconstrained initial values when skipping first-point kinetics
        tau0 = m.t.first()
        if (getattr(args,'constant_hold_up', False) or getattr(args,'mass_balance_slack', False)) and hasattr(m,'q'):
            for ks in getattr(m,'kinetic_species', []):
                if (tau0, ks) in m.q:
                    try:
                        m.q[tau0, ks].set_value(0.0)
                        m.q[tau0, ks].fix(0.0)
                    except Exception:
                        pass
        if (getattr(args,'constant_hold_up', False) or getattr(args,'mass_balance_slack', False)) and hasattr(m,'R'):
            for rx in getattr(m,'product_reactions', []):
                if (tau0, rx) in m.R:
                    try:
                        m.R[tau0, rx].set_value(0.0)
                        m.R[tau0, rx].fix(0.0)
                    except Exception:
                        pass
        # (2) Mass balance slack reformulation (if requested and not using constant hold-up mitigation)
        if getattr(args,'mass_balance_slack', False) and not getattr(args,'constant_hold_up', False):
            if hasattr(m,'mass_balance') and hasattr(m,'Fin'):
                try:
                    m.mass_balance.deactivate()
                except Exception:
                    pass
                m.slack_M = pe.Var(m.t, initialize=0.0)
                def _mb_slack(mdl, t):
                    if t == mdl.t.first() and mdl.current_starting_time == 0:
                        return mdl.M[t] == mdl.M0
                    elif t == mdl.t.first():
                        return pe.Constraint.Skip
                    else:
                        return mdl.dMdt[t] == mdl.final_time * mdl.Fin[t] + mdl.slack_M[t]
                m.mass_balance_slack = pe.Constraint(m.t, rule=_mb_slack)
                m.mass_balance_slack_weight = pe.Param(initialize=float(getattr(args,'mass_balance_slack_weight', 1000.0)), mutable=False)
        # Optional constant hold-up mode: freeze M & feeds, disable mass balance dynamics
        if getattr(args, 'constant_hold_up', False):
            if hasattr(m, 'M'):
                for tau in m.t:
                    try:
                        m.M[tau].fix(init_hold_up)
                    except Exception:
                        pass
            # Zero (and fix) component feeds so Fin -> 0 via fin_link
            for tau in m.t:
                if hasattr(m, 'F_C5liquid'):
                    try:
                        m.F_C5liquid[tau].fix(0.0)
                    except Exception:
                        pass
                if hasattr(m, 'F_liquified_fibers'):
                    try:
                        m.F_liquified_fibers[tau].fix(0.0)
                    except Exception:
                        pass
            if hasattr(m, 'Fin'):
                for tau in m.t:
                    try:
                        m.Fin[tau].fix(0.0)
                    except Exception:
                        pass
            # Deactivate mass balance equality to avoid overconstraint with fixed M & zero Fin
            if hasattr(m, 'mass_balance'):
                try:
                    m.mass_balance.deactivate()
                except Exception:
                    pass
        if last_applied_control is not None:
            for tau in m.t:
                m.F_liquified_fibers[tau].set_value(last_applied_control['F_liquified_fibers'])
                m.F_C5liquid[tau].set_value(last_applied_control['F_C5liquid'])
        # Warm start (primal) from previous horizon solution
        if getattr(args, 'warm_start', False) and prev_solution_snapshot is not None:
            if _apply_warm_start(m, prev_solution_snapshot):
                warm_start_applied_count += 1
        disturbed = _disturb_feed(feed_comp_base, args.disturbance_alpha)
        if hasattr(m, 'Cin'):
            for sp, val in disturbed.items():
                if sp in m.Cin:
                    m.Cin[sp].set_value(val)
        if args.constant_policy:
            status = 'ConstantPolicy'
        else:
            _apply_objective(m, args.economic_objective, args.economic_objective_exact)
            sf = pe.SolverFactory(solver_name)
            prepass_status = None
            if getattr(args, 'feas_prepass', False):
                # Feasibility pre-pass: freeze kinetics & feeds to stabilize M, obtain consistent dMdt.
                frozen_items = []
                try:
                    if hasattr(m, 'q'):
                        for idx in m.q:
                            var = m.q[idx]
                            if not var.fixed:
                                var.set_value(0.0)
                                var.fix(0.0)
                                frozen_items.append(var)
                    if hasattr(m, 'R'):
                        for idx in m.R:
                            var = m.R[idx]
                            if not var.fixed:
                                var.set_value(0.0)
                                var.fix(0.0)
                                frozen_items.append(var)
                    # Optionally stabilize feeds so M derivative not divergent during pre-pass
                    for tau in m.t:
                        if hasattr(m, 'F_C5liquid'):
                            v = m.F_C5liquid[tau]
                            if not v.fixed:
                                v.fix(pe.value(v))
                                frozen_items.append(v)
                        if hasattr(m, 'F_liquified_fibers'):
                            v2 = m.F_liquified_fibers[tau]
                            if not v2.fixed:
                                v2.fix(pe.value(v2))
                                frozen_items.append(v2)
                    # Solve pre-pass silently
                    try:
                        pres = sf.solve(m, tee=False)
                        prepass_status = str(pres.solver.termination_condition)
                    except Exception as _e:
                        prepass_status = f"error:{_e.__class__.__name__}"
                finally:
                    # Unfix kinetics & feeds (leave state variables as is)
                    for var in frozen_items:
                        if var.fixed:
                            try:
                                var.unfix()
                            except Exception:
                                pass
                # Re-apply objective after pre-pass (in case solver modified anything structural)
                _apply_objective(m, args.economic_objective, args.economic_objective_exact)
            # Inject slack penalty if present AFTER objective creation
            if getattr(args,'mass_balance_slack', False) and hasattr(m,'slack_M') and hasattr(m,'mass_balance_slack_weight'):
                try:
                    base_expr = m.obj.expr
                    penalty = m.mass_balance_slack_weight * sum(m.slack_M[t]**2 for t in m.t)
                    if m.obj.sense == pe.minimize:
                        new_expr = base_expr + penalty
                    else:  # maximize
                        new_expr = base_expr - penalty
                    m.del_component(m.obj)
                    m.obj = pe.Objective(expr=new_expr, sense=pe.minimize if False else m.obj.sense)
                except Exception:
                    pass
            # Optional rate scaling normalization: divide q and R expression variables by factor so magnitudes are moderate
            # Variable scaling now handled inside model builder via suffix; placeholder removed.
            res = sf.solve(m, tee=args.tee)
            res = sf.solve(m, tee=args.tee)
            status = str(res.solver.termination_condition)
        # Compute detailed constraint violation diagnostic
        max_con_violation = None
        detailed_violations = []
        try:
            viol = 0.0
            for c in m.component_data_objects(pe.Constraint, active=True):
                if c.body is None:
                    continue
                val = pe.value(c.body)
                lb_vi = ub_vi = 0.0
                if c.has_lb():
                    lb_vi = (c.lower() - val) if val < c.lower() else 0.0
                if c.has_ub():
                    ub_vi = (val - c.upper()) if val > c.upper() else 0.0
                cv = max(lb_vi, ub_vi)
                if cv > 0:
                    detailed_violations.append((cv, c.name))
                viol = max(viol, cv)
            detailed_violations.sort(reverse=True, key=lambda x: x[0])
            max_con_violation = float(viol)
        except Exception:
            max_con_violation = None
            detailed_violations = []
        econ_metric = compute_economic_metric(m)
        # Compute Fin average & delta M for diagnostics
        avg_Fin = None
        delta_M = None
        try:
            if hasattr(m,'Fin'):
                vals = [float(pe.value(m.Fin[tau])) for tau in m.t]
                if vals:
                    avg_Fin = sum(vals)/len(vals)
            if hasattr(m,'M'):
                Mt0 = float(pe.value(m.M[m.t.first()]))
                MtL = float(pe.value(m.M[m.t.last()]))
                delta_M = MtL - Mt0
        except Exception:
            pass
        applied = _extract_applied_control(m)
        last_applied_control = applied.copy()
        interval_vals = {sp: [] for sp in trajectory_species.keys()}
        for tau in m.t:
            abs_t = current_time_s + float(tau) * horizon_s
            if abs_t - current_time_s <= step_s + 1e-9:
                trajectory_time.append(abs_t)
                for sp in trajectory_species.keys():
                    val = float(pe.value(m.C[tau, sp])) if (sp,) else 0.0
                    trajectory_species[sp].append(val)
                    interval_vals[sp].append(val)
                this_M = float(pe.value(m.M[tau]))
                if this_M < 0:  # sanitize tiny negatives
                    if this_M > -1e-6:
                        this_M = 0.0
                trajectory_M.append(this_M)
                # capture controls over the horizon for plotting instead of flat lines
                try:
                    control_series_F_liqfib.append(float(pe.value(m.F_liquified_fibers[tau])))
                    control_series_F_C5.append(float(pe.value(m.F_C5liquid[tau])))
                except Exception:
                    pass
                if not getattr(args, 'no_rates', False):
                    if hasattr(m, 'q') and trajectory_q is None:
                        trajectory_q = {ks: [] for ks in m.kinetic_species}
                    if hasattr(m, 'R') and trajectory_R is None:
                        trajectory_R = {rx: [] for rx in m.product_reactions}
                    if trajectory_q is not None:
                        for ks in m.kinetic_species:
                            vobj = m.q[tau, ks]
                            trajectory_q[ks].append(float(vobj.value) if vobj.value is not None else 0.0)
                    if trajectory_R is not None:
                        for rx in m.product_reactions:
                            vobj = m.R[tau, rx]
                            trajectory_R[rx].append(float(vobj.value) if vobj.value is not None else 0.0)
        neg_species = [sp for sp, series in interval_vals.items() if series and min(series) < -1e-9]
        ethanol_non_monotonic = False
        eth_series = interval_vals.get('Eth', [])
        if len(eth_series) > 1:
            for a, b in zip(eth_series, eth_series[1:]):
                if b < a - 1e-8:
                    ethanol_non_monotonic = True
                    break
        next_time = min(current_time_s + step_s, total_time_s)
        best_tau = None
        best_dist = 1e30
        for tau in m.t:
            abs_t = current_time_s + float(tau) * horizon_s
            if abs_t >= next_time - 1e-9 and abs_t - next_time < best_dist:
                best_tau = tau
                best_dist = abs_t - next_time
        if best_tau is None:
            best_tau = m.t.last()
        predicted_state = {sp: float(pe.value(m.C[best_tau, sp])) for sp in init_conc.keys()}
        predicted_M = float(pe.value(m.M[best_tau]))
        pristine_predicted_state = predicted_state.copy()
        pristine_predicted_M = predicted_M
        realized_state = predicted_state.copy()
        realized_M = predicted_M
        if args.execution_disturbance_alpha > 0:
            # Apply multiplicative noise; guarantee at least one perturbed beyond floating noise.
            perturbed_any = False
            for sp in realized_state.keys():
                factor = 1.0 + random.uniform(-args.execution_disturbance_alpha, args.execution_disturbance_alpha)
                if abs(factor - 1.0) > 1e-12:
                    perturbed_any = True
                realized_state[sp] *= factor
            m_factor = 1.0 + random.uniform(-args.execution_disturbance_alpha, args.execution_disturbance_alpha)
            if abs(m_factor - 1.0) < 1e-12:
                m_factor = 1.0 + 0.5 * args.execution_disturbance_alpha
            realized_M *= m_factor
            # If all species were zero they remain zero under multiplicative noise; inject tiny additive drift
            if args.force_nonzero_drift and all(pristine_predicted_state[s] == 0.0 for s in pristine_predicted_state) and \
               all(realized_state[s] == 0.0 for s in realized_state):
                realized_state['Eth'] = 1e-6  # minimal positive drift to reflect disturbance
        # Clamp realized_M non-negative
        if realized_M < 0:
            realized_M = 0.0
        for sp in init_conc.keys():
            init_conc[sp] = realized_state[sp]
        init_hold_up = realized_M
        drift_l2 = None
        drift_max_abs = None
        if args.execution_disturbance_alpha > 0:
            diffs = [realized_state[s] - pristine_predicted_state[s] for s in pristine_predicted_state.keys()]
            if not getattr(args,'drift_exclude_holdup', False):
                diffs.append(realized_M - pristine_predicted_M)
            drift_l2 = math.sqrt(sum(d*d for d in diffs))
            drift_max_abs = max(abs(d) for d in diffs)
        record = {
            'iteration': k,
            't_start_s': current_time_s,
            't_end_s': next_time,
            'status': status,
            'max_constraint_violation': max_con_violation,
            'top_constraint_violations': [
                {'name': nm, 'violation': float(v)} for v, nm in detailed_violations[:5]
            ] if detailed_violations else [],
            'prepass_status': prepass_status if not args.constant_policy and getattr(args,'feas_prepass', False) else None,
            'applied_control': applied,
            'economic_metric': econ_metric,
            'avg_Fin': avg_Fin,
            'delta_M': delta_M,
            'max_mass_slack': (max(abs(float(pe.value(m.slack_M[t]))) for t in m.t) if getattr(args,'mass_balance_slack', False) and hasattr(m,'slack_M') else None),
            'ethanol_conc_end': init_conc['Eth'],
            'hold_up_end': init_hold_up,
            'neg_species': neg_species,
            'ethanol_non_monotonic': ethanol_non_monotonic,
            'drift_l2': drift_l2,
            'drift_max_abs': drift_max_abs,
            'predicted_end_state': {'C': pristine_predicted_state, 'M': pristine_predicted_M},
            'realized_end_state': {'C': realized_state, 'M': realized_M},
            'min_M_over_horizon': (min(trajectory_M) if trajectory_M else None),
        }
        records.append(record)
        current_time_s = next_time
        if args.checkpoint_interval and args.output and (len(records) % args.checkpoint_interval == 0):
            ck = {
                'meta': {
                    'total_time_h': args.total_time_h,
                    'step_time_h': args.step_time_h,
                    'horizon_time_h': args.horizon_time_h,
                    'iterations': len(records),
                    'solver': solver_name if solver_name else None,
                    'constant_policy': args.constant_policy,
                    'economic_objective': args.economic_objective,
                    'economic_objective_exact': args.economic_objective_exact,
                    'disturbance_alpha': args.disturbance_alpha,
                    'execution_disturbance_alpha': args.execution_disturbance_alpha,
                    'export_step_only': False,
                    'seed': args.seed,
                    'checkpoint_interval': args.checkpoint_interval,
                    'resume_source': args.resume_from,
                    'max_iterations': args.max_iterations,
                },
                'records': records,
                'trajectory': {
                    'time_s': trajectory_time,
                    'species': trajectory_species,
                    'hold_up': trajectory_M,
                },
            }
            if trajectory_q is not None:
                ck['trajectory']['q_series'] = trajectory_q
            if trajectory_R is not None:
                ck['trajectory']['R_series'] = trajectory_R
            # Derive checkpoint filename if directory mode enabled
            if getattr(args,'results_dir', None) and args.output:
                base = os.path.splitext(os.path.basename(args.output))[0]
                ck_name = f"{base}_ck_{len(records):03d}.json"
                ck_path = os.path.join(args.results_dir, ck_name)
                _write_json_atomic(ck_path, ck)
            else:
                _write_json_atomic(args.output, ck)
        # Capture solution for potential warm start of next horizon
        if not args.constant_policy:
            # Only capture snapshot if solver did not mark infeasible (avoid propagating bad point)
            if 'infeasible' not in status.lower():
                prev_solution_snapshot = _capture_primal_solution(m)
            else:
                prev_solution_snapshot = None
        if current_time_s >= total_time_s - 1e-9:
            break

    compressed = False
    if args.export_step_only and trajectory_time:
        indices = []
        last_t = None
        for idx, tval in enumerate(trajectory_time):
            boundary = abs((tval / step_s) - round(tval / step_s)) < 1e-6
            if idx == 0 or boundary or idx == len(trajectory_time) - 1:
                if last_t is None or abs(tval - last_t) > 1e-9:
                    indices.append(idx)
                    last_t = tval
        def _c(d):
            return {k: [v[i] for i in indices] for k, v in d.items()}
        trajectory_time = [trajectory_time[i] for i in indices]
        trajectory_species = _c(trajectory_species)
        trajectory_M = [trajectory_M[i] for i in indices]
        if trajectory_q is not None:
            trajectory_q = _c(trajectory_q)
        if trajectory_R is not None:
            trajectory_R = _c(trajectory_R)
        compressed = True

    cfg_hash = _config_hash(args)
    param_hash = None
    scenario_hash = None
    # If scenario file provided, load it to capture scenario_hash (does not yet drive build)
    if getattr(args, 'scenario', None):
        try:
            from biorefinery.models.scenario_loader import load_scenario
            scn = load_scenario(args.scenario)
            scenario_hash = scn.scenario_hash
        except Exception as e:
            scenario_hash = f"error:{e.__class__.__name__}"
    if getattr(args, 'hash_params', False):
        # Build temporary model snapshot to extract parameter values influencing kinetics
        try:
            mhash = build_fermentation_model(
                n_f_elements_t=1,
                total_f_elements_t=1,
                total_sim_time=1.0,
                current_start_time_seconds=0.0,
                include_kinetics=True,
                detailed_kinetics=args.detailed,
                initial_concentrations={'G':1,'X':1,'Eth':0,'Cell':1,'F':0,'HMF':0,'ACT':0,'CO2':0},
                enable_mass_balance=True,
                feed_control=False,
            )
            param_names = []
            for comp in mhash.component_objects(pe.Param, descend_into=True):
                nm = comp.getname(fully_qualified=True)
                if any(tok in nm.lower() for tok in ['qmax','y_','k0','k1','k2','ki','kip','ksp','gamma','m_']):
                    try:
                        # Handle potentially indexed Params
                        if comp.is_indexed():
                            for idx in comp:
                                param_names.append((f"{nm}[{idx}]", float(pe.value(comp[idx]))))
                        else:
                            param_names.append((nm, float(pe.value(comp))))
                    except Exception:
                        continue
            param_names.sort(key=lambda x: x[0])
            raw = json.dumps(param_names).encode('utf-8')
            param_hash = hashlib.sha256(raw).hexdigest()[:16]
        except Exception:
            param_hash = None
    commit_hash = _git_commit_short()
    result = {
        'meta': {
            'total_time_h': args.total_time_h,
            'step_time_h': args.step_time_h,
            'horizon_time_h': args.horizon_time_h,
            'iterations': len(records),
            'solver': solver_name if solver_name else None,
            'constant_policy': args.constant_policy,
            'constant_hold_up': getattr(args, 'constant_hold_up', False),
            'mass_balance_slack': getattr(args,'mass_balance_slack', False),
            'mass_balance_slack_weight': getattr(args,'mass_balance_slack_weight', None),
            'economic_objective': args.economic_objective,
            'economic_objective_exact': args.economic_objective_exact,
            'disturbance_alpha': args.disturbance_alpha,
            'execution_disturbance_alpha': args.execution_disturbance_alpha,
            'export_step_only': args.export_step_only,
            'seed': args.seed,
            'compressed_applied': compressed,
            'checkpoint_interval': args.checkpoint_interval,
            'resume_source': args.resume_from,
            'max_iterations': args.max_iterations,
            'no_rates': getattr(args, 'no_rates', False),
            'force_nonzero_drift': getattr(args, 'force_nonzero_drift', False),
            'drift_definition': ('l2 and max abs over species' + ('' if getattr(args,'drift_exclude_holdup',False) else ' + hold_up') + ' (pred vs realized after exec disturbance)'),
            'config_hash': cfg_hash,
            'code_commit': commit_hash,
            'param_hash': param_hash,
            'scenario_hash': scenario_hash,
            'warm_start_enabled': getattr(args, 'warm_start', False),
            'warm_start_iterations': warm_start_applied_count,
            'rate_scale': getattr(args,'rate_scale',1.0),
        },
        'records': records,
        'trajectory': {
            'time_s': trajectory_time,
            'species': trajectory_species,
            'hold_up': trajectory_M,
        },
    }
    # Attach control series if captured
    if control_series_F_liqfib and len(control_series_F_liqfib)==len(result['trajectory']['time_s']):
        result['trajectory']['control_series'] = {
            'F_liquified_fibers': control_series_F_liqfib,
            'F_C5liquid': control_series_F_C5,
        }
    if trajectory_q is not None:
        result['trajectory']['q_series'] = trajectory_q
    if trajectory_R is not None:
        result['trajectory']['R_series'] = trajectory_R
    if args.output:
        _write_json_atomic(args.output, result)
    return result


def parse_args():
    p = argparse.ArgumentParser(description='Run ENMPC multi-iteration prototype')
    p.add_argument('--nfe', type=int, default=5, help='Finite elements per horizon')
    p.add_argument('--total-elements', type=int, default=50, help='Total elements batch scaling reference')
    p.add_argument('--total-time-h', type=float, default=190.0, help='Total batch time (h)')
    p.add_argument('--step-time-h', type=float, default=6.0, help='Applied control interval (h)')
    p.add_argument('--horizon-time-h', type=float, default=12.0, help='Prediction horizon length (h)')
    p.add_argument('--solver', default=None, help='Force solver name')
    p.add_argument('--detailed', action='store_true', help='Use detailed kinetics')
    p.add_argument('--economic-objective', action='store_true', help='Use economic metric surrogate objective')
    p.add_argument('--economic-objective-exact', action='store_true', help='Use exact symbolic economic objective instead of surrogate (implies --economic-objective)')
    p.add_argument('--constant-policy', action='store_true', help='Skip optimization (benchmark)')
    p.add_argument('--constant-hold-up', dest='constant_hold_up', action='store_true', help='Mantener M(t) constante: fija M, Fin y feeds a 0 y desactiva mass_balance')
    p.add_argument('--max-concentration', type=float, default=200.0, help='Límite superior para concentraciones (bound en C)')
    p.add_argument('--min-hold-up', type=float, default=100.0, help='Límite inferior para M (evita colapso numérico)')
    p.add_argument('--rate-scale', type=float, default=1.0, help='Factor de normalización conceptual para tasas (placeholder; afecta meta hashing)')
    p.add_argument('--enforce-monotonic-m', action='store_true', help='Imponer M(t) monótonamente no decreciente en el horizonte')
    p.add_argument('--mass-balance-slack', action='store_true', help='Reformular mass_balance con variable slack_M penalizada (diagnóstico)')
    p.add_argument('--mass-balance-slack-weight', type=float, default=1000.0, help='Peso cuadrático para penalización de slack_M^2')
    p.add_argument('--disturbance-alpha', type=float, default=0.0, help='Max relative disturbance on feed compositions')
    p.add_argument('--execution-disturbance-alpha', type=float, default=0.0, help='Relative disturbance applied after prediction to realized state (drift simulation)')
    p.add_argument('--export-step-only', action='store_true', help='Export only step boundary points in trajectory')
    p.add_argument('--no-rates', action='store_true', help='Skip exporting kinetic q_series and R_series to reduce JSON size')
    p.add_argument('--force-nonzero-drift', action='store_true', help='Ensure at least one species shows minimal drift when execution disturbance applied to all-zero predicted state')
    p.add_argument('--ignore-config-hash', action='store_true', help='Allow resume even if configuration hash differs')
    p.add_argument('--drift-exclude-holdup', action='store_true', help='Exclude hold_up term from drift metrics')
    p.add_argument('--hash-params', action='store_true', help='Include a stable hash of selected model parameters in meta (param_hash)')
    p.add_argument('--ignore-param-hash', action='store_true', help='Allow resume even if parameter hash differs (when --hash-params enabled)')
    p.add_argument('--seed', type=int, default=None, help='Random seed for disturbances')
    p.add_argument('--checkpoint-interval', type=int, default=0, help='Write intermediate JSON every N iterations (uncompressed)')
    p.add_argument('--resume-from', default=None, help='Resume from existing ENMPC JSON (must be uncompressed)')
    p.add_argument('--max-iterations', type=int, default=None, help='Limit number of new iterations (useful for staged runs)')
    p.add_argument('--results-dir', default=None, help='Directorio base para guardar outputs y checkpoints (se crea si no existe)')
    p.add_argument('--output', default='enmcp_run.json', help='Archivo JSON (si relativo y --results-dir se usó, se coloca dentro)')
    p.add_argument('--scenario', default=None, help='Optional scenario JSON to embed scenario_hash into meta')
    p.add_argument('--warm-start', action='store_true', help='Reutilizar solución primal previa como inicialización (C, M, feeds, q, R)')
    p.add_argument('--feas-prepass', action='store_true', help='Pre-pase de factibilidad: fija q,R=0 y resuelve antes de liberar')
    p.add_argument('--tee', action='store_true', help='Solver tee output')
    return p.parse_args()


def main():
    args = parse_args()
    if args.economic_objective_exact:
        args.economic_objective = True
    res = run_enmpc(args)
    print(json.dumps({'summary': {
        'iterations': len(res['records']),
        'final_ethanol_conc': res['records'][-1]['ethanol_conc_end'] if res['records'] else None,
        'final_hold_up': res['records'][-1]['hold_up_end'] if res['records'] else None,
    }}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
