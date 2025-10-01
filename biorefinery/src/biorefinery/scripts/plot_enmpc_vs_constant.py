"""Plot comparison between ENMPC optimized run and constant policy benchmark.

Usage example:
  python -m biorefinery.scripts.plot_enmpc_vs_constant \
      --enmcp enmcp_run.json --constant constant_run.json --outdir figures/enmpc

Generates PNGs:
 - concentrations_key.png (G, X, Eth, Cell, CO2)
 - hold_up.png
 - controls.png
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
    # Reconstruct applied control step series from iteration records
    def extract_control(run):
        steps = []
        t = []
        for rec in run['records']:
            mid = 0.5*(rec['t_start_s']+rec['t_end_s'])/3600.0
            t.append(mid)
            steps.append(rec['applied_control']['F_liquified_fibers'])
        return t, steps
    t_en, u_en = extract_control(en)
    t_ct, u_ct = extract_control(ct)
    plt.figure(figsize=(7,4))
    plt.step(t_en, u_en, where='mid', label='Fibers ENMPC')
    plt.step(t_ct, u_ct, where='mid', linestyle='--', label='Fibers Const')
    # (Optional future: add second axis for C5 if policy diverges)
    plt.xlabel('Time [h]')
    plt.ylabel('F_liquified_fibers [kg/s]')
    plt.legend()
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
    plot_hold_up(en, ct, args.outdir)
    plot_controls(en, ct, args.outdir)
    plot_economic_metric(en, ct, args.outdir)
    print(f"Saved plots to {args.outdir}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
