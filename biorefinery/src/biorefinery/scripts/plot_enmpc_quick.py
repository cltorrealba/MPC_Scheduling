from __future__ import annotations
"""Quick plotting utility for a single ENMPC run JSON.

Generates standard plots: concentrations (key & all), hold-up, controls, economic metric, drift (if present).

Usage:
  python -m biorefinery.scripts.plot_enmpc_quick --run path/to/run.json --outdir figures/quick
"""
import argparse, json, os
import matplotlib.pyplot as plt

KEY_SPECIES = ['G','X','Eth','Cell','CO2']


def _load(path: str):
    with open(path,'r',encoding='utf-8') as f:
        return json.load(f)


def plot_concentrations(run, outdir):
    t = [x/3600.0 for x in run['trajectory']['time_s']]
    species_block = run['trajectory']['species']
    # Key subset
    plt.figure(figsize=(8,5))
    for sp in KEY_SPECIES:
        if sp in species_block:
            plt.plot(t, species_block[sp], label=sp)
    plt.xlabel('Time [h]'); plt.ylabel('Concentration [g/kg]'); plt.legend(); plt.tight_layout()
    plt.savefig(os.path.join(outdir,'concentrations_key.png'), dpi=140); plt.close()
    # All species
    plt.figure(figsize=(9,6))
    for sp, arr in species_block.items():
        plt.plot(t, arr, label=sp)
    plt.xlabel('Time [h]'); plt.ylabel('Concentration [g/kg]'); plt.legend(ncol=2, fontsize=8); plt.tight_layout()
    plt.savefig(os.path.join(outdir,'concentrations_all.png'), dpi=140); plt.close()


def plot_hold_up(run, outdir):
    if 'hold_up' not in run['trajectory']:
        return
    t = [x/3600.0 for x in run['trajectory']['time_s']]
    plt.figure(figsize=(7,4))
    plt.plot(t, run['trajectory']['hold_up'], label='Hold-up')
    plt.xlabel('Time [h]'); plt.ylabel('Hold-up [kg]'); plt.legend(); plt.tight_layout()
    plt.savefig(os.path.join(outdir,'hold_up.png'), dpi=140); plt.close()


def plot_controls(run, outdir):
    if 'records' not in run:
        return
    t_mid = []
    u_fibers = []
    u_c5 = []
    for rec in run['records']:
        mid = 0.5*(rec['t_start_s']+rec['t_end_s'])/3600.0
        t_mid.append(mid)
        ctrl = rec.get('applied_control', {})
        u_fibers.append(ctrl.get('F_liquified_fibers', 0.0))
        u_c5.append(ctrl.get('F_c5_feed', 0.0))
    plt.figure(figsize=(7,4))
    plt.step(t_mid, u_fibers, where='mid', label='Fibers')
    if any(v != 0 for v in u_c5):
        plt.step(t_mid, u_c5, where='mid', label='C5 feed')
    plt.xlabel('Time [h]'); plt.ylabel('Feed [kg/s]'); plt.legend(); plt.tight_layout()
    plt.savefig(os.path.join(outdir,'controls.png'), dpi=140); plt.close()


def plot_economic(run, outdir):
    if 'records' not in run:
        return
    t = []
    econ = []
    for rec in run['records']:
        t.append(rec['t_end_s']/3600.0)
        econ.append(rec.get('economic_metric', 0.0))
    plt.figure(figsize=(7,4))
    plt.plot(t, econ, marker='o')
    plt.xlabel('Time [h]'); plt.ylabel('Economic metric'); plt.tight_layout()
    plt.savefig(os.path.join(outdir,'economic_metric.png'), dpi=140); plt.close()


def plot_drift(run, outdir):
    drift = run.get('drift_metrics')
    if not drift:
        return
    t = [x/3600.0 for x in run['trajectory']['time_s']]
    # For each recorded drift series (assumed arrays aligned with time)
    for key, arr in drift.items():
        if not isinstance(arr, list) or len(arr) != len(t):
            continue
        plt.figure(figsize=(7,4))
        plt.plot(t, arr, label=key)
        plt.xlabel('Time [h]'); plt.ylabel(key); plt.tight_layout()
        plt.savefig(os.path.join(outdir,f'drift_{key}.png'), dpi=140); plt.close()


def parse_args():
    p = argparse.ArgumentParser(description='Quick plotting for a single ENMPC run JSON')
    p.add_argument('--run', required=True, help='Path to ENMPC run JSON file produced by run_enmpc')
    p.add_argument('--outdir', default='figures/quick', help='Output directory')
    return p.parse_args()


def main():
    args = parse_args()
    data = _load(args.run)
    os.makedirs(args.outdir, exist_ok=True)
    plot_concentrations(data, args.outdir)
    plot_hold_up(data, args.outdir)
    plot_controls(data, args.outdir)
    plot_economic(data, args.outdir)
    plot_drift(data, args.outdir)
    print(f"Saved quick ENMPC plots to {args.outdir}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
