"""Plot comparison between ENMPC optimized run and constant policy benchmark.

Usage example:
  python -m biorefinery.scripts.plot_enmpc_vs_constant \
      --enmcp enmcp_run.json --constant constant_run.json --outdir figures/enmpc

Generates PNGs:
 - concentrations_key.png (G, X, Eth, Cell, CO2)
 - concentrations_subplots.png (un subplot por especie)
 - hold_up.png
 - controls.png (dos subplots: F_liquified_fibers y F_C5liquid)
 - economic_metric.png (iteration-wise)
"""
from __future__ import annotations
import json
import argparse
import os
import math
import matplotlib.pyplot as plt

KEY_SPECIES = ['G','X','Eth','Cell','CO2']


def _load(path: str):
    with open(path,'r',encoding='utf-8') as f:
        return json.load(f)


def plot_concentrations(en, ct, outdir):
    t_en = [x/3600.0 for x in en['trajectory']['time_s']]
    t_ct = [x/3600.0 for x in ct['trajectory']['time_s']]
    for sp in KEY_SPECIES:
        if sp not in en['trajectory']['species']:
            continue
    plt.figure(figsize=(8,5))
    for sp in KEY_SPECIES:
        if sp in en['trajectory']['species']:
            plt.plot(t_en, en['trajectory']['species'][sp], label=f"{sp} ENMPC")
        if sp in ct['trajectory']['species']:
            plt.plot(t_ct, ct['trajectory']['species'][sp], '--', label=f"{sp} Const")
    plt.xlabel('Time [h]')
    plt.ylabel('Concentration [g/kg]')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir,'concentrations_key.png'), dpi=140)
    plt.close()


def plot_hold_up(en, ct, outdir):
    t_en = [x/3600.0 for x in en['trajectory']['time_s']]
    t_ct = [x/3600.0 for x in ct['trajectory']['time_s']]
    plt.figure(figsize=(7,4))
    plt.plot(t_en, en['trajectory']['hold_up'], label='Hold-up ENMPC')
    plt.plot(t_ct, ct['trajectory']['hold_up'], '--', label='Hold-up Const')
    plt.xlabel('Time [h]')
    plt.ylabel('Hold-up [kg]')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir,'hold_up.png'), dpi=140)
    plt.close()


def plot_controls(en, ct, outdir):
    # Prefer full horizon control_series if available; fallback to iteration steps
    def clamp_nonneg(vals, tol=1e-8):
        return [v if v is None else (0.0 if v < 0 and v > -tol else (v if v >= 0 else 0.0)) for v in vals]

    def from_control_series(run):
        traj = run.get('trajectory', {})
        if 'control_series' in traj and 'time_s' in traj:
            t = [x/3600.0 for x in traj['time_s']]
            series = traj['control_series']
            ff = clamp_nonneg(series.get('F_liquified_fibers', []))
            fc5 = clamp_nonneg(series.get('F_C5liquid', []))
            if len(ff) == len(t) and len(fc5) == len(t):
                return t, ff, fc5
        return None

    def from_records(run):
        t = []
        ff = []
        fc5 = []
        for rec in run.get('records', []):
            mid = 0.5*(rec['t_start_s']+rec['t_end_s'])/3600.0
            t.append(mid)
            u = rec.get('applied_control', {})
            ff.append(float(u.get('F_liquified_fibers', 0.0)))
            fc5.append(float(u.get('F_C5liquid', 0.0)))
        return t, ff, fc5

    en_data = from_control_series(en) or from_records(en)
    ct_data = from_control_series(ct) or from_records(ct)
    t_en, ff_en, fc5_en = en_data
    t_ct, ff_ct, fc5_ct = ct_data

    fig, axes = plt.subplots(1, 2, figsize=(12,4), sharex=True)
    axes[0].step(t_en, ff_en, where='post', label='Fibers ENMPC')
    axes[0].step(t_ct, ff_ct, where='post', linestyle='--', label='Fibers Const')
    axes[0].set_ylabel('F_liquified_fibers [kg/s]')
    axes[0].set_xlabel('Time [h]')
    axes[0].legend()

    axes[1].step(t_en, fc5_en, where='post', label='C5 ENMPC')
    axes[1].step(t_ct, fc5_ct, where='post', linestyle='--', label='C5 Const')
    axes[1].set_ylabel('F_C5liquid [kg/s]')
    axes[1].set_xlabel('Time [h]')
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(os.path.join(outdir,'controls.png'), dpi=140)
    plt.close()


def plot_economic_metric(en, ct, outdir):
    def extract_metric(run):
        t = []
        v = []
        for rec in run['records']:
            t.append(rec['t_end_s']/3600.0)
            v.append(rec['economic_metric'])
        return t, v
    t_en, v_en = extract_metric(en)
    t_ct, v_ct = extract_metric(ct)
    plt.figure(figsize=(7,4))
    plt.plot(t_en, v_en, label='Economic ENMPC')
    plt.plot(t_ct, v_ct, '--', label='Economic Const')
    plt.xlabel('Time [h]')
    plt.ylabel('Economic metric')
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(outdir,'economic_metric.png'), dpi=140)
    plt.close()


def parse_args():
    p = argparse.ArgumentParser(description='Plot ENMPC vs constant policy results')
    p.add_argument('--enmcp', required=True, help='JSON result of optimized ENMPC run')
    p.add_argument('--constant', required=True, help='JSON result of constant policy run')
    p.add_argument('--outdir', default='figures/enmpc', help='Output directory for PNGs')
    return p.parse_args()


def main():
    args = parse_args()
    en = _load(args.enmcp)
    ct = _load(args.constant)
    os.makedirs(args.outdir, exist_ok=True)
    plot_concentrations(en, ct, args.outdir)
    # Additional subplot view: one subplot per species
    try:
        species_keys = sorted(set(list(en['trajectory']['species'].keys()) + list(ct['trajectory']['species'].keys())))
        n = len(species_keys)
        ncols = 3 if n >= 3 else n
        nrows = math.ceil(n / max(1, ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(4*ncols, 3*nrows), squeeze=False)
        t_en = [x/3600.0 for x in en['trajectory']['time_s']]
        t_ct = [x/3600.0 for x in ct['trajectory']['time_s']]
        for idx, sp in enumerate(species_keys):
            r = idx // ncols
            c = idx % ncols
            ax = axes[r][c]
            if sp in en['trajectory']['species']:
                ax.plot(t_en, en['trajectory']['species'][sp], label=f"ENMPC")
            if sp in ct['trajectory']['species']:
                ax.plot(t_ct, ct['trajectory']['species'][sp], '--', label=f"Const")
            ax.set_title(sp)
            ax.set_xlabel('Time [h]')
            ax.set_ylabel('[g/kg]')
            ax.legend(fontsize='small')
        # Hide any empty subplots
        for k in range(n, nrows*ncols):
            r = k // ncols; c = k % ncols
            axes[r][c].axis('off')
        plt.tight_layout()
        plt.savefig(os.path.join(args.outdir, 'concentrations_subplots.png'), dpi=140)
        plt.close()
    except Exception:
        pass
    plot_hold_up(en, ct, args.outdir)
    plot_controls(en, ct, args.outdir)
    plot_economic_metric(en, ct, args.outdir)
    print(f"Saved plots to {args.outdir}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
