from __future__ import annotations
import subprocess, sys, datetime, platform
from typing import Dict, Any


def gather_run_metadata(extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    # Git commit
    try:
        commit = subprocess.check_output(['git','rev-parse','--short','HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        commit = None
    meta['git_commit'] = commit
    # Dirty flag
    try:
        status = subprocess.check_output(['git','status','--porcelain'], stderr=subprocess.DEVNULL, text=True)
        meta['git_dirty'] = bool(status.strip())
    except Exception:
        meta['git_dirty'] = None
    meta['python_version'] = sys.version.split()[0]
    meta['platform'] = platform.platform()
    meta['timestamp_utc'] = datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z'
    if extra:
        meta.update(extra)
    return meta
