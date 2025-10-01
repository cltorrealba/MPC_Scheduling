import hashlib
from typing import Iterable, Tuple
import pyomo.environ as pe

# Core parameter name patterns to include in structural hash
PARAM_PREFIXES = [
    'qmax_', 'Y_', 'KI_', 'KIP_', 'KSP_', 'gamma_', 'm_', 'K0G', 'K1G', 'K2G', 'K0X', 'K1X', 'K2X'
]

# Exclusions (exact names) if any parameter should be ignored
EXCLUDE = set()


def _collect_param_values(model) -> Iterable[Tuple[str, float]]:
    for comp in model.component_objects(pe.Param, descend_into=True):
        name = comp.getname()
        if not any(name.startswith(pref) for pref in PARAM_PREFIXES):
            continue
        if name in EXCLUDE:
            continue
        try:
            # Pyomo 6+: Params always have an index set; scalar if dim()==0
            is_scalar = (comp.dim() == 0)
        except Exception:
            # Fallback: attempt direct value extraction, if fails treat as indexed
            try:
                val = float(pe.value(comp))
                yield name, val
                continue
            except Exception:
                is_scalar = False
        if is_scalar:
            try:
                yield name, float(pe.value(comp))
            except Exception:
                pass
        else:
            for idx in comp:
                try:
                    val = float(pe.value(comp[idx]))
                except Exception:
                    continue
                yield f"{name}[{idx}]", val


def compute_param_hash(model) -> str:
    items = list(_collect_param_values(model))
    # Stable ordering
    items.sort(key=lambda x: x[0])
    m = hashlib.sha256()
    for k, v in items:
        m.update(k.encode('utf-8'))
        m.update(b'=')
        m.update(repr(round(v, 10)).encode('utf-8'))
        m.update(b'\n')
    # Truncate for readability
    return m.hexdigest()[:16]
