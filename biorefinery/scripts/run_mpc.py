"""Entry point wrapper to run the original Fermentation_Scheduling_and_MPC script.

This keeps legacy script intact while we progressively refactor into the biorefinery package.

Usage (after activating venv and installing requirements):
    python -m biorefinery.scripts.run_mpc --solver knitro --time-limit 600

For now this just executes the legacy script via runpy. Later we will:
 - Expose a function build_and_run(case: str, scenario_path: str, ...)
 - Parameterize data paths
 - Add logging & JSON index mapping
"""
from __future__ import annotations
import argparse
import pathlib
import runpy
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LEGACY_SCRIPT = REPO_ROOT / "biorefinery_models" / "Fermentation_Scheduling_and_MPC.py"


def parse_args():
    p = argparse.ArgumentParser(description="Run legacy Fermentation Scheduling + MPC model")
    p.add_argument("--solver", default="knitro", help="(Futuro) Solver preferido para subproblemas")
    p.add_argument("--time-limit", type=int, default=1800, help="(Futuro) Límite de tiempo global (s)")
    p.add_argument("--scenario", default=None, help="(Pendiente) Nombre de escenario JSON normalizado")
    p.add_argument("--init-json", default=None, help="Ruta explícita a archivo de inicialización existente")
    p.add_argument("--tee", action="store_true", help="Mostrar salida detallada del solver si se integra")
    return p.parse_args()


def main():
    args = parse_args()
    if not LEGACY_SCRIPT.exists():
        print(f"No se encuentra el script legado en {LEGACY_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    # Por ahora simplemente ejecutamos el script legado en su propio namespace.
    # Futuro: interceptar funciones, inyectar parámetros, controlar salidas.
    runpy.run_path(str(LEGACY_SCRIPT), run_name="__main__")


if __name__ == "__main__":  # pragma: no cover
    main()
