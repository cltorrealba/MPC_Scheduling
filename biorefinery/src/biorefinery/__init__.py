"""Biorefinery package initializer.

Mantiene imports pesados (numpy, pyomo, etc.) fuera de la carga inicial
para acelerar discovery de tests que sólo requieren submódulos ligeros.

Se exponen nombres a través de __all__, pero los imports concretos se
realizan de forma perezosa cuando el usuario accede a los atributos.
"""

from importlib import import_module

_LAZY_MODULES = {
	"optimization": "biorefinery.optimization",
	"models": "biorefinery.models",
}

# Hint for static analyzers: declare names as None; replaced on first access.
optimization = None  # type: ignore
models = None  # type: ignore

def __getattr__(name):  # pragma: no cover - comportamiento estándar
	if name in _LAZY_MODULES:
		module = import_module(_LAZY_MODULES[name])
		globals()[name] = module
		return module
	raise AttributeError(name)

from .logging_config import get_logger  # noqa: E402,F401  (ligero)

__all__ = ["optimization", "models", "get_logger"]
