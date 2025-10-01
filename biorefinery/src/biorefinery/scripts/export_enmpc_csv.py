from __future__ import annotations
import argparse, json, csv, sys, math
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser(description='Export ENMPC JSON to CSV (time/species/hold_up/optional rates)')
    p.add_argument('input', help='Input ENMPC JSON file')
    p.add_argument('--prefix', default='enmcp_export', help='Output CSV prefix')
    p.add_argument('--include-rates', action='store_true', help='Export q_series and R_series if present')
    return p.parse_args()

def main():
    args = parse_args()
    data = json.loads(Path(args.input).read_text())
    traj = data['trajectory']
    time = traj['time_s']
    species = traj['species']
    hold_up = traj['hold_up']
    rows = []
    header = ['time_s','hold_up'] + list(species.keys())
    if args.include_rates:
        q_series = traj.get('q_series', {})
        r_series = traj.get('R_series', {})
        header += [f"q:{k}" for k in q_series.keys()] + [f"R:{k}" for k in r_series.keys()]
    for i, t in enumerate(time):
        row = [t, hold_up[i]]
        for sp in species.keys():
            row.append(species[sp][i])
        if args.include_rates:
            for k, arr in traj.get('q_series', {}).items():
                row.append(arr[i])
            for k, arr in traj.get('R_series', {}).items():
                row.append(arr[i])
        rows.append(row)
    out_path = Path(f"{args.prefix}_trajectory.csv")
    with out_path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    # Controls per iteration
    recs = data['records']
    ctrl_header = ['iteration','t_start_s','t_end_s'] + sorted(next(iter(recs))['applied_control'].keys()) if recs else []
    ctrl_rows = []
    for r in recs:
        base = [r['iteration'], r['t_start_s'], r['t_end_s']]
        for k in sorted(r['applied_control'].keys()):
            base.append(r['applied_control'][k])
        ctrl_rows.append(base)
    if ctrl_header:
        ctrl_path = Path(f"{args.prefix}_controls.csv")
        with ctrl_path.open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(ctrl_header)
            writer.writerows(ctrl_rows)
    print(f"Exported {out_path} and controls CSV (if any)")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
