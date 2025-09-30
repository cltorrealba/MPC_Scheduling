"""Lightweight public API for optimization subpackage.

Converted to lazy imports to prevent heavy transitive imports (legacy serializer,
GAMS-related helpers) when only small utilities like dsda_adapter are needed.
"""

__all__ = [
    "dsda_enumeration",
    "evaluate_neighbors",
    "do_line_search",
    "external_ref",
    "get_external_information",
    "extvars_gdp_to_mip",
    "find_actual_neighbors",
    "solve_subproblem",
    "preprocess_problem",
    "load_initialization",
    "dump_initialization",
]

def __getattr__(name):
    if name == "dsda_enumeration":
        from .dsda import dsda_enumeration as f
        return f
    if name in ("evaluate_neighbors", "do_line_search"):
        from .evaluation import evaluate_neighbors, do_line_search
        return {"evaluate_neighbors": evaluate_neighbors, "do_line_search": do_line_search}[name]
    if name in ("external_ref", "get_external_information", "extvars_gdp_to_mip"):
        from .external_ref import external_ref, get_external_information, extvars_gdp_to_mip
        return {
            "external_ref": external_ref,
            "get_external_information": get_external_information,
            "extvars_gdp_to_mip": extvars_gdp_to_mip,
        }[name]
    if name == "find_actual_neighbors":
        from .neighborhoods import find_actual_neighbors
        return find_actual_neighbors
    if name in ("solve_subproblem", "preprocess_problem"):
        from .solvers import solve_subproblem, preprocess_problem
        return {"solve_subproblem": solve_subproblem, "preprocess_problem": preprocess_problem}[name]
    if name in ("load_initialization", "dump_initialization"):
        from .initialization import load_initialization, dump_initialization
        return {"load_initialization": load_initialization, "dump_initialization": dump_initialization}[name]
    raise AttributeError(name)
