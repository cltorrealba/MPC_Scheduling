from __future__ import annotations
import csv, argparse, pathlib, json
import math

try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None


def load_rows(path: pathlib.Path):
    with path.open('r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def safe_float(v):
    try:
        if v in (None, ''):
            return math.nan
        return float(v)
    except Exception:
        return math.nan


def _load_batches(log_dir: pathlib.Path):
    steps_dir = log_dir / 'steps'
    if not steps_dir.exists():
        return None
    batches_series = []  # list of (step_index, nbatches)
    for jf in sorted(steps_dir.glob('step_*.json')):
        try:
            data = json.load(jf.open())
            idx = data.get('step_row', {}).get('step_index')
            batches = data.get('raw', {}).get('scheduling', {}).get('batches', {})
            if idx is not None:
                batches_series.append((idx, len(batches)))
        except Exception:
            continue
    return batches_series if batches_series else None

def plot(args):
    csv_path = pathlib.Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f'CSV not found: {csv_path}')
    rows = load_rows(csv_path)
    t = [safe_float(r['t_end_h']) for r in rows]
    ethanol = [safe_float(r['ethanol_applied_pred']) for r in rows]
    drift_l2 = [safe_float(r['drift_l2']) for r in rows]
    drift_l2_avg = [safe_float(r.get('drift_l2_avg')) for r in rows]
    econ = [safe_float(r.get('economic_metric2') or r.get('economic_metric')) for r in rows]
    batches_series = _load_batches(csv_path.parent)
    if plt is None:
        print('matplotlib no disponible; imprimiendo últimas filas:')
        for r in rows[-5:]:
            print(r)
        return
    nrows = 4 if batches_series else 3
    fig, ax = plt.subplots(nrows,1, figsize=(7,3*nrows), sharex=True)
    ax[0].plot(t, ethanol, marker='o')
    ax[0].set_ylabel('Ethanol (applied)')
    ax[1].plot(t, drift_l2, label='drift_l2', marker='x')
    if any(not math.isnan(x) for x in drift_l2_avg):
        ax[1].plot(t, drift_l2_avg, label='drift_l2_avg', linestyle='--')
    ax[1].set_ylabel('Drift')
    ax[1].legend()
    ax[2].plot(t, econ, marker='s', color='tab:green')
    ax[2].set_ylabel('Economic')
    if batches_series:
        idx, nb = zip(*batches_series)
        ax[3].bar(idx, nb, color='tab:purple', alpha=0.7)
        ax[3].set_ylabel('#Batches')
        ax[3].set_xlabel('Step Index')
    else:
        ax[2].set_xlabel('Absolute Time (h)')
    fig.tight_layout()
    if args.output:
        fig.savefig(args.output, dpi=150)
        print('Saved figure to', args.output)
    else:
        plt.show()


def build_parser():
    p = argparse.ArgumentParser(description='Quick plot for rolling EMPC CSV results')
    p.add_argument('--csv', required=True, help='Path to rolling_performance_log.csv')
    p.add_argument('--output', help='Optional PNG output path')
    return p


if __name__ == '__main__':  # pragma: no cover
    args = build_parser().parse_args()
    plot(args)
