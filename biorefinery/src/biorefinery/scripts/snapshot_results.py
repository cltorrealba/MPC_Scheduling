"""Snapshot bundler for ENMPC / DSDA run artifacts.

Creates a ZIP archive containing selected JSON, CSV, PNG files and a manifest with hashes for reproducibility.

Usage:
  python -m biorefinery.scripts.snapshot_results --inputs results/exp01 --patterns *.json *.png *.csv \
    --output snapshots/exp01_snapshot.zip --relative-to results

Features:
- Collect files from multiple paths (directories or individual files).
- Glob pattern filtering.
- Optional exclusion globs.
- Manifest (JSON) inside ZIP: list of files with SHA256 and size.
- Root trimming: store relative paths from a base prefix (`--relative-to`).
- Dry-run listing.
"""
from __future__ import annotations
import argparse, os, fnmatch, json, hashlib, zipfile, sys
from typing import List, Dict


def parse_args():
    p = argparse.ArgumentParser(description='Bundle snapshot (ZIP) of run artifacts with manifest hash')
    p.add_argument('--inputs', nargs='+', required=True, help='Archivos o directorios base a incluir')
    p.add_argument('--patterns', nargs='*', default=['*.json','*.png','*.csv'], help='Glob de inclusión')
    p.add_argument('--exclude', nargs='*', default=[], help='Globs a excluir')
    p.add_argument('--relative-to', default=None, help='Recortar prefijo común (directorio base) en rutas almacenadas')
    p.add_argument('--output', required=True, help='Archivo ZIP resultante')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--quiet', action='store_true')
    return p.parse_args()

def match_any(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)

def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def collect_files(inputs: List[str], include: List[str], exclude: List[str]):
    files = []
    for item in inputs:
        if os.path.isdir(item):
            for root, _dirs, fnames in os.walk(item):
                for fn in fnames:
                    if not match_any(fn, include):
                        continue
                    if exclude and match_any(fn, exclude):
                        continue
                    files.append(os.path.join(root, fn))
        elif os.path.isfile(item):
            fn = os.path.basename(item)
            if match_any(fn, include) and not (exclude and match_any(fn, exclude)):
                files.append(item)
    return sorted(files)

def main():
    args = parse_args()
    files = collect_files(args.inputs, args.patterns, args.exclude)
    if not files:
        print('No files matched', file=sys.stderr)
        return 1
    base = os.path.abspath(args.relative_to) if args.relative_to else None
    manifest = []
    for f in files:
        rel = f
        if base and os.path.commonpath([base, os.path.abspath(f)]) == base:
            rel = os.path.relpath(f, base)
        h = file_hash(f)
        sz = os.path.getsize(f)
        manifest.append({'path': rel, 'sha256': h, 'size': sz})
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode('utf-8')).hexdigest()
    if args.dry_run:
        if not args.quiet:
            for m in manifest:
                print(f"Would add: {m['path']} size={m['size']} sha256={m['sha256'][:12]}")
            print(f"manifest_count={len(manifest)} manifest_hash={manifest_hash}")
        return 0
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for m in manifest:
            arc = m['path']
            # Reconstruct full original path
            full = os.path.join(base, arc) if base else m['path']
            zf.write(full, arc)
        zf.writestr('MANIFEST.json', json.dumps({'files': manifest, 'manifest_hash': manifest_hash}, indent=2))
    if not args.quiet:
        print(f"Created snapshot: {args.output} files={len(manifest)} manifest_hash={manifest_hash}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
