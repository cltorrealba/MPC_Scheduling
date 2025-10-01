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
    m = build_fermentation_model(
        n_f_elements_t=args.nfe,
        total_f_elements_t=args.total_elements,
        total_sim_time=args.total_time_h * 3600.0,
        current_start_time_seconds=current_start_s,
        include_kinetics=True,
        detailed_kinetics=args.detailed,
        initial_concentrations=init_conc,
        enable_mass_balance=True,
        feed_control=False,
    )
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
            'execution_disturbance_alpha','export_step_only','seed','no_rates','force_nonzero_drift','drift_exclude_holdup']
    payload = {k: getattr(args, k, None) for k in keys}
    raw = json.dumps(payload, sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _git_commit_short():
    try:
        out = subprocess.check_output(['git','rev-parse','--short','HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
        return out or None
    except Exception:
        return None


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
    trajectory_q = None
    trajectory_R = None
    current_time_s = 0.0
    last_applied_control = None

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

    for k in range(start_idx, n_iters):
        if (k - start_idx) >= max_new:
            break
        m = _build_model(args, current_time_s, init_conc, init_hold_up)
        apply_feed_profile(m, DEFAULT_PHASES, override_existing=True)
        if last_applied_control is not None:
            for tau in m.t:
                m.F_liquified_fibers[tau].set_value(last_applied_control['F_liquified_fibers'])
                m.F_C5liquid[tau].set_value(last_applied_control['F_C5liquid'])
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
            res = sf.solve(m, tee=args.tee)
            status = str(res.solver.termination_condition)
        econ_metric = compute_economic_metric(m)
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
                trajectory_M.append(float(pe.value(m.M[tau])))
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
            'applied_control': applied,
            'economic_metric': econ_metric,
            'ethanol_conc_end': init_conc['Eth'],
            'hold_up_end': init_hold_up,
            'neg_species': neg_species,
            'ethanol_non_monotonic': ethanol_non_monotonic,
            'drift_l2': drift_l2,
            'drift_max_abs': drift_max_abs,
            'predicted_end_state': {'C': pristine_predicted_state, 'M': pristine_predicted_M},
            'realized_end_state': {'C': realized_state, 'M': realized_M},
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
            _write_json_atomic(args.output, ck)
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
        },
        'records': records,
        'trajectory': {
            'time_s': trajectory_time,
            'species': trajectory_species,
            'hold_up': trajectory_M,
        },
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
    p.add_argument('--output', default='enmcp_run.json', help='Result JSON file')
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
