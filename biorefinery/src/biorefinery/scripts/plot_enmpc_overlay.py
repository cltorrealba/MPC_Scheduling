"""Overlay plots for multiple ENMPC run JSON files.

Usage:
  python -m biorefinery.scripts.plot_enmpc_overlay --runs run1.json run2.json ... \
     --species Eth,G,X --output overlay_eth.png

Features:
 - Flexible selection of species (comma or repeated flag)
 - Optional time normalization to hours
 - Auto color cycle & legend with short labels (file stem)
 - Optional separate panel per species or single figure
"""
from __future__ import annotations
import argparse, json, os, csv
from typing import List, Dict, Any
import matplotlib.pyplot as plt


def parse_args():
    p = argparse.ArgumentParser(description='Overlay ENMPC trajectories')
    p.add_argument('--runs', nargs='+', required=True, help='JSON result files de ENMPC')
    p.add_argument('--species', default='Eth', help='Lista separada por coma de especies a graficar')
    p.add_argument('--per-species-panels', action='store_true', help='Un subplot por especie')
    p.add_argument('--normalize-hours', action='store_true', help='Convertir tiempo (s) a horas')
    p.add_argument('--plot-holdup', action='store_true', help='Añadir panel / curva de hold-up M(t)')
    p.add_argument('--plot-controls', action='store_true', help='Graficar señales de control (F_liquified_fibers, F_C5liquid) si están disponibles')
    p.add_argument('--plot-rates', default=None, help='Lista separada por coma de tasas (q species o R reactions) para graficar si existen (q_series / R_series)')
    p.add_argument('--export-csv', default=None, help='Exportar datos combinados a CSV (wide format)')
    p.add_argument('--filter-run-contains', default=None, help='Filtrar runs cuyo nombre de archivo contenga este substring (después de cargar)')
    p.add_argument('--filter-run-exclude', default=None, help='Excluir runs cuyo nombre contenga este substring')
    p.add_argument('--title', default=None)
    p.add_argument('--output', default=None, help='Archivo PNG (si no se especifica muestra la ventana)')
    p.add_argument('--output-dir', default=None, help='Directorio destino para PNG y CSV (se crea)')
    p.add_argument('--width', type=float, default=10.0)
    p.add_argument('--height', type=float, default=5.0)
    p.add_argument('--per-run-columns', action='store_true', help='Organiza los panels en columnas por run (comparación lado a lado)')
    p.add_argument('--monotonic-style-hint', action='store_true', help='Detecta meta.enforce_monotonic_m y aplica estilo (línea sólida) vs punteada')
    p.add_argument('--annotate-stats', action='store_true', help='Añade min/max hold-up y último valor en título del panel de M')
    return p.parse_args()


def load_run(path:str):
    with open(path,'r',encoding='utf-8') as f:
        return json.load(f)


def main():
    args = parse_args()
    species = [s.strip() for s in args.species.split(',') if s.strip()]
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        if args.output and not os.path.isabs(args.output):
            args.output = os.path.join(args.output_dir, args.output)
        if args.export_csv and not os.path.isabs(args.export_csv):
            args.export_csv = os.path.join(args.output_dir, args.export_csv)
    runs_data = []
    for p in args.runs:
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        data = load_run(p)
        runs_data.append((p, data))
    # Filters
    if args.filter_run_contains:
        runs_data = [rd for rd in runs_data if args.filter_run_contains in os.path.basename(rd[0])]
    if args.filter_run_exclude:
        runs_data = [rd for rd in runs_data if args.filter_run_exclude not in os.path.basename(rd[0])]
    if not runs_data:
        raise SystemExit("No runs left after filtering")
    rate_targets = []
    if args.plot_rates:
        rate_targets = [r.strip() for r in args.plot_rates.split(',') if r.strip()]
    # Determine figure structure
    # Determine number of panels
    base_species_panels = len(species) if args.per_species_panels else 1
    extra_panels = 0
    holdup_panel = args.plot_holdup
    control_panel = args.plot_controls
    rates_panel = bool(rate_targets)
    panel_order = []
    # Species panels first
    if args.per_species_panels:
        for sp in species:
            panel_order.append(('species', sp))
    else:
        panel_order.append(('species_combo', ','.join(species)))
    if holdup_panel:
        panel_order.append(('holdup', None))
    if control_panel:
        panel_order.append(('control', None))
    if rates_panel:
        panel_order.append(('rates', None))
    n_panels = len(panel_order)
    if args.per_run_columns:
        # Create grid: rows = panels, cols = runs
        fig, axes_all = plt.subplots(n_panels, len(runs_data), figsize=(args.width * len(runs_data), args.height * n_panels), sharex='col')
        if n_panels == 1:
            axes_all = [axes_all]
    else:
        fig, axes_all = plt.subplots(n_panels, 1, figsize=(args.width, args.height * n_panels), sharex=True)
        if n_panels == 1:
            axes_all = [axes_all]
    # Prepare combined CSV collector
    combined_rows: List[Dict[str, Any]] = []
    time_key = 'time_h' if args.normalize_hours else 'time_s'
    for idx,(ptype, tag) in enumerate(panel_order):
        if args.per_run_columns:
            row_axes = axes_all[idx]
            if len(runs_data)==1:
                row_axes = [row_axes]
        else:
            row_axes = [axes_all[idx]]
        for col_idx,(path, payload) in enumerate(runs_data):
            ax = row_axes[col_idx] if args.per_run_columns else row_axes[0]
            traj = payload.get('trajectory', {})
            times = traj.get('time_s', [])
            times_plot = [t / 3600.0 for t in times] if args.normalize_hours else times
            label = os.path.splitext(os.path.basename(path))[0]
            style = '-'
            if args.monotonic_style_hint:
                meta = payload.get('meta', {})
                if not meta.get('enforce_monotonic_m') and meta.get('constant_hold_up') is False:
                    style = '--'
            if ptype.startswith('species'):
                if ptype == 'species_combo':
                    for sp in species:
                        series = traj.get('species', {}).get(sp)
                        if series is None:
                            continue
                        ax.plot(times_plot, series, style, label=f"{label}:{sp}")
                        # CSV rows
                        if args.export_csv:
                            for tval, sval in zip(times_plot, series):
                                combined_rows.append({'run': label, time_key: tval, 'type': 'species', 'name': sp, 'value': sval})
                else:  # individual species panel
                    sp = tag
                    series = traj.get('species', {}).get(sp)
                    if series is None:
                        continue
                    ax.plot(times_plot, series, style, label=label)
                    if args.export_csv:
                        for tval, sval in zip(times_plot, series):
                            combined_rows.append({'run': label, time_key: tval, 'type': 'species', 'name': sp, 'value': sval})
                ax.set_ylabel('Concentration')
            elif ptype == 'holdup':
                hold = traj.get('hold_up', [])
                if hold:
                    ax.plot(times_plot, hold, style, label=label)
                    if args.export_csv:
                        for tval, sval in zip(times_plot, hold):
                            combined_rows.append({'run': label, time_key: tval, 'type': 'hold_up', 'name': 'M', 'value': sval})
                ax.set_ylabel('Hold-up M')
            elif ptype == 'control':
                ctrl_series = traj.get('control_series', {}) or {}
                # If full series present, plot them; else fallback to first record as flat line
                plotted_any = False
                for cname in ['F_liquified_fibers','F_C5liquid']:
                    series = ctrl_series.get(cname)
                    if series and len(series)==len(times_plot):
                        ax.plot(times_plot, series, style, label=f"{label}:{cname}")
                        plotted_any = True
                        if args.export_csv:
                            for tval, sval in zip(times_plot, series):
                                combined_rows.append({'run': label, time_key: tval, 'type': 'control', 'name': cname, 'value': sval})
                if not plotted_any:
                    recs = payload.get('records', [])
                    if recs:
                        f1 = recs[0].get('applied_control', {})
                        for cname in ['F_liquified_fibers','F_C5liquid']:
                            if cname in f1:
                                ax.plot(times_plot, [f1[cname]]*len(times_plot), style, label=f"{label}:{cname}")
                                if args.export_csv:
                                    for tval in times_plot:
                                        combined_rows.append({'run': label, time_key: tval, 'type': 'control', 'name': cname, 'value': f1[cname]})
                ax.set_ylabel('Control')
            elif ptype == 'rates':
                q_series = payload.get('trajectory', {}).get('q_series', {}) or {}
                R_series = payload.get('trajectory', {}).get('R_series', {}) or {}
                for rt in rate_targets:
                    if rt in q_series:
                        series = q_series[rt]
                        ax.plot(times_plot, series, style, label=f"{label}:q[{rt}]")
                        if args.export_csv:
                            for tval, sval in zip(times_plot, series):
                                combined_rows.append({'run': label, time_key: tval, 'type': 'rate_q', 'name': rt, 'value': sval})
                    elif rt in R_series:
                        series = R_series[rt]
                        ax.plot(times_plot, series, style, label=f"{label}:R[{rt}]")
                        if args.export_csv:
                            for tval, sval in zip(times_plot, series):
                                combined_rows.append({'run': label, time_key: tval, 'type': 'rate_R', 'name': rt, 'value': sval})
                ax.set_ylabel('Rates')
        # Per-row formatting
        if args.per_run_columns:
            for cax,(path, payload) in zip(row_axes, runs_data):
                cax.grid(alpha=0.3)
                if ptype != 'species_combo':
                    cax.legend(fontsize='xx-small')
            if ptype == 'holdup' and args.annotate_stats:
                for cax,(path,payload) in zip(row_axes, runs_data):
                    hold = payload.get('trajectory',{}).get('hold_up',[])
                    if hold:
                        stats = f"min={min(hold):.3f}\nmax={max(hold):.3f}\nfinal={hold[-1]:.3f}"
                        cax.text(0.99,0.02, stats, transform=cax.transAxes, ha='right', va='bottom', fontsize=8,
                                 bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.6, lw=0.5))
        else:
            ax = row_axes[0]
            ax.grid(alpha=0.3)
            if ptype != 'species_combo':
                ax.legend(fontsize='x-small', ncol=3)
            if ptype == 'holdup' and args.annotate_stats:
                hold_series = []
                for path,payload in runs_data:
                    hold = payload.get('trajectory',{}).get('hold_up',[])
                    if hold:
                        hold_series.append((os.path.splitext(os.path.basename(path))[0], hold))
                y0 = 0.02
                for lbl, hs in hold_series:
                    ax.text(0.99, y0, f"{lbl}: min={min(hs):.3f} max={max(hs):.3f} fin={hs[-1]:.3f}", transform=ax.transAxes,
                            ha='right', va='bottom', fontsize=7,
                            bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.5, lw=0.3))
                    y0 += 0.06
    # Legend for combined species panel
    if not args.per_run_columns:
        if panel_order and panel_order[0][0] == 'species_combo':
            axes_all[0].legend(fontsize='x-small', ncol=4)
        axes_all[-1].set_xlabel('Time (h)' if args.normalize_hours else 'Time (s)')
    else:
        # Set bottom row x-labels (axes_all is 2D array when per_run_columns=True)
        bottom_row = axes_all[-1] if n_panels>1 else axes_all[0]
        # bottom_row is either a numpy ndarray of column axes or a single axis
        try:
            import numpy as _np
            if isinstance(bottom_row, _np.ndarray):
                iterable_axes = list(bottom_row.flat)
            else:
                iterable_axes = [bottom_row]
        except Exception:
            # Fallback generic
            iterable_axes = bottom_row if isinstance(bottom_row, (list, tuple)) else [bottom_row]
        for ax in iterable_axes:
            ax.set_xlabel('Time (h)' if args.normalize_hours else 'Time (s)')
    if args.title:
        fig.suptitle(args.title)
    fig.tight_layout()
    if args.export_csv and combined_rows:
        fieldnames = ['run', time_key, 'type', 'name', 'value']
        with open(args.export_csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(combined_rows)
        print(f"Exported CSV -> {args.export_csv}")
    if args.output:
        fig.savefig(args.output, dpi=180)
        print(f"Saved overlay plot -> {args.output}")
    else:
        plt.show()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
