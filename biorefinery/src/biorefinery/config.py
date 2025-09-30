"""Central configuration utilities for the biorefinery package.

Loads defaults from constants with optional override via environment variables.
Intended to remove scattered magic numbers / strings (solver names, time limits).
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from .logging_config import get_logger, set_level as _set_log_level

log = get_logger("config")


def _env(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return v


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        log.warning("Invalid float for %s=%r; using default %s", name, raw, default)
        return default


@dataclass(slots=True)
class SolverConfig:
    primary_nlp: str = _env("BIOREF_SOLVER_NLP", "ipopt")
    primary_minlp: str = _env("BIOREF_SOLVER_MINLP", "bonmin")
    time_limit: float = _env_float("BIOREF_TIME_LIMIT", 3600.0)
    tee: bool = bool(int(os.getenv("BIOREF_SOLVER_TEE", "0")))

    def as_dict(self):  # convenience
        return {
            "primary_nlp": self.primary_nlp,
            "primary_minlp": self.primary_minlp,
            "time_limit": self.time_limit,
            "tee": self.tee,
        }


_config_singleton: Optional[SolverConfig] = None


def get_config(force_reload: bool = False) -> SolverConfig:
    global _config_singleton
    if _config_singleton is None or force_reload:
        _config_singleton = SolverConfig()
        log.debug("Loaded SolverConfig: %s", _config_singleton.as_dict())
    return _config_singleton


def set_logging_level(level: str):
    """Programmatically adjust logging level at runtime."""
    _set_log_level(level)
    log.info("Logging level set to %s", level)


__all__ = ["SolverConfig", "get_config", "set_logging_level"]
