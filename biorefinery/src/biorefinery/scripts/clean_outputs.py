"""Utility script to clean generated result artifacts (JSON/CSV/PNG) safely.

Usage examples:
  python -m biorefinery.scripts.clean_outputs --paths results/exp01 results/mono_comp \
     --patterns *.json *.png --exclude *baseline* --dry-run

  python -m biorefinery.scripts.clean_outputs --paths results --older-than-days 7 --patterns *.png

Features:
- Pattern matching (glob) per provided directory (non recursive unless --recursive).
- Optional age filter (modification time older than N days).
- Exclusions by glob patterns.
- Dry-run mode prints what would be deleted.
- Summary report of counts.

Limitations:
- Does not remove directories.
- Ignores files larger than a safety threshold unless --no-size-guard (default 200 MB) to prevent accidental big deletions.
"""
from __future__ import annotations
import argparse, os, fnmatch, time, sys, gzip, shutil, hashlib
from typing import List, Tuple

SAFETY_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


def parse_args():
    p = argparse.ArgumentParser(description="Clean result artifacts (JSON/CSV/PNG) by pattern and age")
    p.add_argument('--paths', nargs='+', required=True, help='Directorios base a limpiar')
    p.add_argument('--patterns', nargs='*', default=['*.json','*.csv','*.png'], help='Globs de archivos a considerar')
    p.add_argument('--exclude', nargs='*', default=[], help='Globs a excluir')
    p.add_argument('--recursive', action='store_true', help='Recorrer subdirectorios')
    p.add_argument('--older-than-days', type=int, default=None, help='Eliminar/comprimir solo si mtime > N días')
    p.add_argument('--dry-run', action='store_true', help='Mostrar archivos sin borrar')
    p.add_argument('--no-size-guard', action='store_true', help='Desactivar protección de tamaño (>=200MB)')
    p.add_argument('--quiet', action='store_true', help='Reducir salida (solo resumen final)')
    p.add_argument('--action', choices=['delete','compress'], default='delete', help='Acción sobre candidatos: borrar o comprimir a .gz')
    p.add_argument('--keep-latest', type=int, default=0, help='Preservar los N archivos más recientes que coincidan antes de aplicar acción')
    p.add_argument('--hash-manifest', action='store_true', help='Imprime hash SHA256 concatenado de paths candidatos (audit)')
    return p.parse_args()


def match_any(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def main():
    args = parse_args()
    now = time.time()
    cutoff = None
    if args.older_than_days is not None:
        cutoff = now - args.older_than_days * 86400
    total = 0
    kept = 0
    removed = 0
    candidates: List[Tuple[str,float]] = []  # (path, mtime)
    for base in args.paths:
        if not os.path.isdir(base):
            if not args.quiet:
                print(f"Skip (no dir): {base}")
            continue
        walker = os.walk(base) if args.recursive else [(base, [], os.listdir(base))]
        for root, _dirs, files in walker:
            for fname in files:
                fpath = os.path.join(root, fname)
                if not match_any(fname, args.patterns):
                    continue
                if args.exclude and match_any(fname, args.exclude):
                    continue
                try:
                    st = os.stat(fpath)
                except OSError:
                    continue
                if cutoff and st.st_mtime > cutoff:
                    kept += 1
                    continue
                if (not args.no_size_guard) and st.st_size >= SAFETY_SIZE_BYTES:
                    if not args.quiet:
                        print(f"Guard keep (size>=200MB): {fpath}")
                    kept += 1
                    continue
                candidates.append((fpath, st.st_mtime))
    # Ordenar candidatos por mtime descendente para aplicar keep-latest
    candidates.sort(key=lambda x: x[1], reverse=True)
    if args.keep_latest > 0:
        preserve = candidates[:args.keep_latest]
        candidates = candidates[args.keep_latest:]
        kept += len(preserve)
    paths_only = [p for p,_ in candidates]
    total = len(paths_only) + kept
    if args.hash_manifest and paths_only:
        h = hashlib.sha256('\n'.join(paths_only).encode('utf-8')).hexdigest()
        print(f"manifest_hash={h}")
    if not args.quiet:
        verb = 'Would remove' if args.dry_run and args.action=='delete' else \
               'Would compress' if args.dry_run and args.action=='compress' else \
               'Removing' if args.action=='delete' else 'Compressing'
        for f in paths_only:
            print(f"{verb}: {f}")
    if not args.dry_run:
        for f in paths_only:
            try:
                if args.action == 'delete':
                    os.remove(f)
                else:  # compress
                    gz_path = f + '.gz'
                    with open(f,'rb') as fin, gzip.open(gz_path,'wb') as fout:
                        shutil.copyfileobj(fin, fout)
                    os.remove(f)
                removed += 1
            except OSError as e:
                print(f"Error {args.action} {f}: {e}")
    summary = {
        'evaluated_files': total,
        'affected': removed if not args.dry_run else 0,
        'would_affect': len(paths_only) if args.dry_run else None,
        'kept': kept,
        'patterns': args.patterns,
        'exclude': args.exclude,
        'recursive': args.recursive,
        'older_than_days': args.older_than_days,
        'dry_run': args.dry_run,
        'action': args.action,
        'keep_latest': args.keep_latest,
    }
    print(summary)
    return 0

if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
