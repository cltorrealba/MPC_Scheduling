from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser(description='Validate ENMPC JSON structure and optional hashes')
    p.add_argument('input', help='Input ENMPC JSON')
    p.add_argument('--require-hash', action='store_true', help='Fail if config_hash missing')
    p.add_argument('--print-summary', action='store_true', help='Print concise run summary')
    return p.parse_args()

def main():
    args = parse_args()
    data = json.loads(Path(args.input).read_text())
    meta = data.get('meta', {})
    required_meta = ['total_time_h','step_time_h','iterations','compressed_applied']
    for k in required_meta:
        if k not in meta:
            print(f"ERROR: meta key missing: {k}", file=sys.stderr)
            return 1
    if args.require_hash and not meta.get('config_hash'):
        print('ERROR: config_hash required but missing', file=sys.stderr)
        return 1
    recs = data.get('records', [])
    if not recs:
        print('ERROR: no records', file=sys.stderr)
        return 1
    traj = data.get('trajectory', {})
    time = traj.get('time_s', [])
    if not time:
        print('ERROR: empty trajectory time', file=sys.stderr)
        return 1
    # Basic consistency: lengths align
    for sp, arr in traj.get('species', {}).items():
        if len(arr) != len(time):
            print(f"ERROR: species length mismatch {sp}", file=sys.stderr)
            return 1
    if args.print_summary:
        last = recs[-1]
        print(json.dumps({'iterations': len(recs), 'final_ethanol': last.get('ethanol_conc_end'), 'final_hold_up': last.get('hold_up_end')}, indent=2))
    else:
        print('OK')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
