"""Central logging configuration for biorefinery package."""
from __future__ import annotations
import logging
import os
import sys

_LOG_FORMAT = "[%(levelname)s] %(asctime)s | %(name)s | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_default_handler = logging.StreamHandler(stream=sys.stdout)
_default_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))

root = logging.getLogger("biorefinery")
if not root.handlers:
    level_name = os.getenv("BIOREF_LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))
    root.addHandler(_default_handler)


def get_logger(name: str):
    return root.getChild(name)


def set_level(level: str):
    """Adjust root biorefinery logger level dynamically."""
    lvl = getattr(logging, level.upper(), None)
    if not isinstance(lvl, int):  # fallback silently
        lvl = logging.INFO
    root.setLevel(lvl)
    for h in root.handlers:
        h.setLevel(lvl)
