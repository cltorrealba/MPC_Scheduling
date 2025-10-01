"""Initialization helpers wrapping legacy json serialization logic.

This module provides a thin abstraction so future refactors can replace the
JSON persistence without touching calling code.
"""
from __future__ import annotations
from dataclasses import dataclass
import pathlib
from typing import Optional, Any

# We still rely on legacy model_serializer located in the original folder for now.
# Later we will copy and refactor it into biorefinery/models/serialization.py
import runpy
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_LEGACY_DIR = _REPO_ROOT / "biorefinery_models"

# Load legacy serializer symbols dynamically (isolated namespace)
_serializer_ns = runpy.run_path(str(_LEGACY_DIR / "model_serializer.py"))
StoreSpec = _serializer_ns["StoreSpec"]
from_json = _serializer_ns["from_json"]
to_json = _serializer_ns["to_json"]


@dataclass
class InitConfig:
    model_name: str = ""
    starting: bool = False
    human_read: bool = True
    custom_weights: Any = None  # Could be a StoreSpec override


def initialization_file_path(model_name: str, starting: bool = False) -> pathlib.Path:
    if model_name:
        fname = f"{model_name}_initialization.json"
    else:
        fname = "dsda_initialization.json"
    return _LEGACY_DIR / fname


def load_initialization(m, json_path: Optional[pathlib.Path] = None, from_feasible: bool = False, feasible_model: str = ""):
    wts = StoreSpec.value()
    if json_path is None:
        if from_feasible and feasible_model:
            json_path = initialization_file_path(feasible_model, starting=True)
        else:
            json_path = initialization_file_path("")
    from_json(m, fname=str(json_path), wts=wts)
    return m


def dump_initialization(m, cfg: InitConfig) -> pathlib.Path:
    wts = cfg.custom_weights if cfg.custom_weights is not None else StoreSpec.value()
    path = initialization_file_path(cfg.model_name, starting=cfg.starting)
    # Remove stray space in import alias earlier (safe):
    _serializer_ns["to_json"](m, fname=str(path), human_read=cfg.human_read, wts=wts)
    return path

# --- Legacy compatibility shim ---
def initialize_model(m, json_path=None, from_feasible: bool = False, feasible_model: str = ""):
    """Shim matching older signature expected by legacy modules.

    Delegates to load_initialization. Kept minimal to avoid side effects.
    """
    return load_initialization(m, json_path=json_path, from_feasible=from_feasible, feasible_model=feasible_model)

def generate_initialization(m, starting_initialization: bool = False, model_name: str = "", human_read: bool = True, wts=None):
    """Legacy shim writing initialization JSON.

    Args mirror legacy signature; returns path string for compatibility.
    """
    cfg = InitConfig(model_name=model_name, starting=starting_initialization, human_read=human_read, custom_weights=wts)
    path = dump_initialization(m, cfg)
    return str(path)
