from __future__ import annotations
"""Scenario loading and validation utilities.

Converts JSON scenario files into internal dataclasses for fermentation and scheduling layers.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
import json, random

try:
    import jsonschema  # type: ignore
except ImportError:  # fallback gentle failure
    jsonschema = None  # type: ignore

from .api_contract import FermentationConfig
from .scheduling_minimal import (
    SchedulingConfig, TaskDef, UnitDef
)

SCHEMA_FILENAME = "schema.json"

@dataclass
class LoadedScenario:
    raw: Dict[str, Any]
    fermentation: FermentationConfig
    scheduling: SchedulingConfig
    seed: int
    name: str


def _load_schema(schema_path: Path) -> Dict[str, Any]:
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_scenario(raw: Dict[str, Any], schema: Dict[str, Any]):
    if jsonschema is None:
        # Soft warning if validation library not present
        return
    jsonschema.validate(instance=raw, schema=schema)


def _build_fermentation(cfg: Dict[str, Any]) -> FermentationConfig:
    return FermentationConfig(
        horizon_h=cfg.get("horizon_h", 12.0),
        nfe=cfg.get("nfe", 5),
        total_elements_reference=cfg.get("total_elements_reference", 50),
        include_kinetics=cfg.get("include_kinetics", True),
        detailed_kinetics=cfg.get("detailed_kinetics", False),
        enable_mass_balance=cfg.get("enable_mass_balance", True),
        include_dilution=cfg.get("include_dilution", False),
        feed_control=cfg.get("feed_control", False),
        initial_concentrations=cfg.get("initial_concentrations", {}),
        initial_hold_up=cfg.get("initial_hold_up", 1000.0),
    )


def _build_scheduling(cfg: Dict[str, Any]) -> SchedulingConfig:
    tasks = [
        TaskDef(
            name=t["name"],
            inputs=t.get("inputs", {}),
            outputs=t.get("outputs", {}),
            units=t.get("units", []),
            min_batch=t.get("min_batch", 0.0),
            max_batch=t.get("max_batch", 0.0),
            process_time_h=t.get("process_time_h", 0.0),
        ) for t in cfg.get("tasks", [])
    ]
    units = [UnitDef(name=u["name"], kind=u.get("kind")) for u in cfg.get("units", [])]
    demand_pairs: List[Tuple[str,int,float]] = []
    for d in cfg.get("demand", []):
        demand_pairs.append((d["state"], int(d["t"]), float(d["value"])))
    demand_map = {(s, t): v for s, t, v in demand_pairs}
    return SchedulingConfig(
        horizon_h=cfg.get("horizon_h", 12.0),
        n_periods=cfg.get("n_periods", 12),
        tasks=tasks,
        units=units,
        states=cfg.get("states", []),
        initial_inventory=cfg.get("initial_inventory", {}),
        storage_capacity=cfg.get("storage_capacity", {}),
        demand=demand_map,
    )


def load_scenario(path: str | Path) -> LoadedScenario:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    schema_path = path.parent / SCHEMA_FILENAME
    if schema_path.exists():
        schema = _load_schema(schema_path)
        validate_scenario(raw, schema)
    seed = int(raw.get("seed", 0))
    random.seed(seed)
    fermentation = _build_fermentation(raw.get("fermentation", {}))
    scheduling = _build_scheduling(raw.get("scheduling", {}))
    return LoadedScenario(
        raw=raw,
        fermentation=fermentation,
        scheduling=scheduling,
        seed=seed,
        name=raw.get("name", path.stem),
    )

__all__ = ["LoadedScenario", "load_scenario", "validate_scenario"]
