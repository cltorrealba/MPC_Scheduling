# Release Notes v0.3.0 (Fase 3)

## Overview
Foco en estabilidad numérica ENMPC, exploración discreta multi-start con cache persistente y visualización avanzada multi-run.

## Destacados
- Estabilización con bounds parametrizables y opción de monotonicidad para el hold-up.
- Slack de balance de masa para diagnóstico controlado de infeasibilidades.
- Multi-start DSDA persistente con cache incremental (evita reevaluaciones).
- Overlay mejorado (paneles configurables, modo columnas, stats, export CSV unificada).
- Organización de resultados en carpetas dedicadas (`--results-dir`, `--output-dir`).

## Incompatibilidades / Cambios Potenciales
- `config_hash` ahora incluye nuevos flags; corridas previas no podrán reanudarse sin `--ignore-config-hash` si difieren.
- Formato JSON: campos nuevos (`control_series`, `min_M_over_horizon`). Scripts externos deben tolerar su presencia.

## Pasos Recomendados Pre-Tag
1. Ejecutar suite de tests: `pytest -q`.
2. Regenerar baseline si cambió solver: `set BIOREF_REFRESH_BASELINE=1; pytest -k validation_baseline -q`.
3. Correr ejemplo básico (`docs/examples/enmpc_basic.md`) para verificar paths.
4. Confirmar ausencia de artefactos negativos en M con `--enforce-monotonic-m`.

## Crear Tag
```powershell
git add .
git commit -m "release: v0.3.0"
git tag -a v0.3.0 -m "Fase 3 estable"
git push origin HEAD --tags
```

## Próximo Ciclo (Preview)
- Penalización suave a variación de M.
- Integración DSDA intra-horizonte.
- Dashboard interactivo.
- Métrica económica extendida (cost feeds, energía).
