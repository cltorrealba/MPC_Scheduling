from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser(description='Merge multiple uncompressed ENMPC runs (same config_hash)')
    p.add_argument('inputs', nargs='+', help='Input ENMPC JSON files in chronological order')
    p.add_argument('--output', required=True, help='Merged output JSON')
    p.add_argument('--allow-hash-mismatch', action='store_true', help='Proceed even if config_hash differs')
    p.add_argument('--compress', action='store_true', help='Apply export_step_only style compression after merge')
    return p.parse_args()

def compress_traj(time_s, species, hold_up, q_series=None, R_series=None, step_s=None):
    if not time_s:
        return time_s, species, hold_up, q_series, R_series
    if step_s is None:
        return time_s, species, hold_up, q_series, R_series
    indices = []
    last_t = None
    for i,t in enumerate(time_s):
        boundary = abs((t/step_s) - round(t/step_s)) < 1e-6
        if i==0 or boundary or i==len(time_s)-1:
            if last_t is None or abs(t-last_t) > 1e-9:
                indices.append(i); last_t=t
    def sub(v): return [v[i] for i in indices]
    species_c = {k: sub(v) for k,v in species.items()}
    hold_c = sub(hold_up)
    if q_series: q_series = {k: sub(v) for k,v in q_series.items()}
    if R_series: R_series = {k: sub(v) for k,v in R_series.items()}
    time_c = sub(time_s)
    return time_c, species_c, hold_c, q_series, R_series

def main():
    args = parse_args()
    merged = None
    for path in args.inputs:
        data = json.loads(Path(path).read_text())
        if data['meta'].get('export_step_only'):
            print(f"ERROR: Cannot merge compressed run: {path}", file=sys.stderr); return 1
        if merged is None:
            merged = data
            continue
        # Hash check
        if (merged['meta'].get('config_hash') != data['meta'].get('config_hash')) and not args.allow_hash_mismatch:
            print(f"ERROR: config_hash mismatch between {args.inputs[0]} and {path}", file=sys.stderr)
            return 1
        # Append records adjusting iteration numbering
        offset = len(merged['records'])
        for r in data['records']:
            nr = r.copy()
            nr['iteration'] = offset + nr['iteration']
            merged['records'].append(nr)
        # Append trajectory
        mt = merged['trajectory']['time_s']
        dt_full = data['trajectory']['time_s']
        # Determine slice start to avoid duplicate boundary point(s)
        start_idx = 0
        if mt and dt_full:
            while start_idx < len(dt_full) and abs(mt[-1] - dt_full[start_idx]) < 1e-9:
                start_idx += 1
        dt = dt_full[start_idx:]
        merged['trajectory']['time_s'].extend(dt)
        for k,v in data['trajectory']['species'].items():
            merged['trajectory']['species'][k].extend(v[start_idx:])
        merged['trajectory']['hold_up'].extend(data['trajectory']['hold_up'][start_idx:])
        if 'q_series' in data['trajectory']:
            mq = merged['trajectory'].setdefault('q_series', {k:[] for k in data['trajectory']['q_series']})
            for k,v in data['trajectory']['q_series'].items():
                mq.setdefault(k,[]).extend(v[start_idx:])
        if 'R_series' in data['trajectory']:
            mr = merged['trajectory'].setdefault('R_series', {k:[] for k in data['trajectory']['R_series']})
            for k,v in data['trajectory']['R_series'].items():
                mr.setdefault(k,[]).extend(v[start_idx:])
        merged['meta']['iterations'] = len(merged['records'])
    if merged is None:
        print('ERROR: no inputs processed', file=sys.stderr); return 1
    # Deduplicate consecutive identical time stamps (possible due to per-iteration boundary duplication within individual runs)
    t_series = merged['trajectory']['time_s']
    if t_series:
        keep_indices = [0]
        for i in range(1, len(t_series)):
            if abs(t_series[i] - t_series[keep_indices[-1]]) > 1e-9:
                keep_indices.append(i)
        if len(keep_indices) != len(t_series):
            merged['trajectory']['time_s'] = [t_series[i] for i in keep_indices]
            for k, v in merged['trajectory']['species'].items():
                merged['trajectory']['species'][k] = [v[i] for i in keep_indices]
            hu = merged['trajectory']['hold_up']
            merged['trajectory']['hold_up'] = [hu[i] for i in keep_indices]
            if 'q_series' in merged['trajectory']:
                for k, v in merged['trajectory']['q_series'].items():
                    merged['trajectory']['q_series'][k] = [v[i] for i in keep_indices]
            if 'R_series' in merged['trajectory']:
                for k, v in merged['trajectory']['R_series'].items():
                    merged['trajectory']['R_series'][k] = [v[i] for i in keep_indices]
    if args.compress:
        step_s = merged['meta'].get('step_time_h',0)*3600.0
        t,species,hold_up,q_series,R_series = compress_traj(
            merged['trajectory']['time_s'],
            merged['trajectory']['species'],
            merged['trajectory']['hold_up'],
            merged['trajectory'].get('q_series'),
            merged['trajectory'].get('R_series'),
            step_s=step_s
        )
        merged['trajectory']['time_s']=t
        merged['trajectory']['species']=species
        merged['trajectory']['hold_up']=hold_up
        if q_series:
            merged['trajectory']['q_series']=q_series
        if R_series:
            merged['trajectory']['R_series']=R_series
        merged['meta']['compressed_applied']=True
        merged['meta']['export_step_only']=True
    Path(args.output).write_text(json.dumps(merged, indent=2))
    print(f"Merged -> {args.output}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
