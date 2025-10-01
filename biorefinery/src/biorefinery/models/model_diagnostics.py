import pyomo.environ as pe


def constraint_residual(con):
    try:
        body = pe.value(con.body)
        if con.equality:
            return abs(body - pe.value(con.lower))
        # For ranged constraints, take max violation
        low_v = 0.0
        up_v = 0.0
        if con.has_lb():
            low_v = max(0.0, pe.value(con.lower) - body)
        if con.has_ub():
            up_v = max(0.0, body - pe.value(con.upper))
        return max(low_v, up_v)
    except Exception:
        return float('nan')


def collect_top_violations(model, limit=20, min_threshold=1e-6):
    data = []
    for con in model.component_data_objects(pe.Constraint, active=True):
        viol = constraint_residual(con)
        if viol is None or viol != viol:  # NaN check
            continue
        if viol >= min_threshold:
            data.append((viol, con.name))
    data.sort(reverse=True, key=lambda x: x[0])
    return data[:limit]


def print_diagnostics(model, header="Diagnostics", limit=20):
    print(f"=== {header} ===")
    top = collect_top_violations(model, limit=limit)
    if not top:
        print("No violations above threshold.")
        return top
    for v, name in top:
        print(f"{v:.4g} : {name}")
    return top

__all__ = ["collect_top_violations", "print_diagnostics"]
