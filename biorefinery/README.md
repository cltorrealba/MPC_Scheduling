# Biorefinery Modeling & ENMPC Diagnostics

Este submódulo contiene el modelo de fermentación Pyomo (DAE) y utilidades para generación de baseline unificado y ejecución de un lazo ENMPC experimental.

## Componentes principales

- `src/biorefinery/models/fermentation.py`: Constructor del modelo de fermentación (`build_fermentation_model`). Parametrizable vía argumentos (nfe, horizonte, cinéticas, bounds, etc.).
- `src/biorefinery/scripts/generate_unified_baseline.py`: Genera un JSON baseline estable para pruebas (series de concentraciones, tasas y finales dinámicos) con hashing de parámetros.
- `src/biorefinery/scripts/run_enmpc.py`: Lazo ENMPC receding-horizon con soporte a warm start, perturbaciones y métricas de drift.
- `src/biorefinery/models/model_diagnostics.py`: Utilidades para recolectar residuales de restricciones (diagnóstico puntual).

## Flags y parámetros clave (Factibilidad & Diagnóstico)

### Control de bounds (estrategia A & D)
- `max_concentration` (default 200.0): Límite superior (g/kg) aplicado a todas las concentraciones `C[t,sp]`. Evita inflación numérica cuando el solver intenta compensar inconsistencias dinámicas.
- `min_hold_up` (default 100.0): Límite inferior en `M(t)` (kg) que previene el colapso trivial de la masa (M→0) que degenera las ecuaciones `M * dC/dt = ...`.

Ambos se pasan como argumentos en `build_fermentation_model` y están expuestos en `run_enmpc.py` (`--max-concentration`, `--min-hold-up`). Se documentan en el propio código.

### Baseline generator
Flags relevantes de `generate_unified_baseline.py` (ya integrados):
- `--feasible-seed`: Genera baseline determinista sin solver (concentraciones constantes / tasas cero) para asegurar reproducibilidad cuando hay inestabilidad temporal.
- `--fallback-if-infeasible`: Si el solver marca infeasible, produce baseline de reserva etiquetado (`solver=ipopt+fallback`).
- `--diagnose`: Imprime ranking de violaciones de restricciones pre y post solve; ayuda a identificar la ecuación dominante.

### ENMPC loop (`run_enmpc.py`)
- `--feas-prepass`: Pre-pase de factibilidad: fija q,R, feeds para estabilizar `M` y obtener un estado consistente antes de liberar cinéticas.
- `--mass-balance-slack`: Reformula la ecuación de balance de masa con un slack `slack_M[t]` (solo diagnóstico). Desactiva la restricción original `mass_balance` y agrega nueva: `dMdt = final_time * Fin + slack_M`.
- `--mass-balance-slack-weight <w>`: Peso cuadrático para penalizar `sum(slack_M[t]^2)`. Default 1000.0.
- Métrica exportada: `max_mass_slack` en cada record JSON para cuantificar la discrepancia que el slack absorbió.

Uso típico (diagnóstico de infeasibilidad):
```
python -m biorefinery.scripts.run_enmpc \
  --total-time-h 12 --step-time-h 6 --horizon-time-h 12 \
  --nfe 2 --total-elements 10 --max-iterations 1 \
  --feas-prepass --mass-balance-slack --mass-balance-slack-weight 5000 \
  --output diag_slack.json
```
Si `max_mass_slack` es grande y el solver converge, indica el orden de magnitud de la inconsistencia estructural. Si además `M` colapsa cerca del bound inferior y las concentraciones se inflan, revisar límites y formulación.

### Estrategia de estabilización aplicada
1. Unificar condición inicial de `M` mediante parámetro `M0` (evita mismatch de ecuación inicial vs bounds).
2. Ajustar bounds: `min_hold_up` >= 100, `max_concentration` <= 200.
3. (Opcional) Slack temporal para medir brecha (ya no necesario tras corrección, se mantiene para futuros diagnósticos).
4. Re-ejecutar baseline sin fallback y confirmar `status=optimal` y violaciones ~1e-12.

### Interpretación rápida de diagnósticos
- Residuales enormes en `Diff_mass` o `mass_balance`: verificar inicialización de `M` y feeds.
- Muchos "No value for uninitialized VarData" en pre-solve: ruido benigno antes de que el DAE se discretice totalmente; observar solo el ranking luego del solve.
- `max_constraint_violation` ~1e-9 o menor: numéricamente aceptable.

## Buenas prácticas
- Usar `--feasible-seed` para regenerar baseline rápido después de cambios de cinética antes de confiar en soluciones dinámicas completas.
- Añadir commits atómicos cuando cambie `param_hash` o se actualice baseline para mantener trazabilidad.
- Evitar introducir simultáneamente nuevas ecuaciones dinámicas y modificar bounds sin primero verificar con `--diagnose`.

## Próximos pasos sugeridos
- Documentar un ejemplo mínimo de integración de escenario (`--scenario`) y hashing de parámetros (`--hash-params`).
- Añadir pruebas unitarias para asegurar que `--mass-balance-slack` reporta cero slack en un caso nominal estable.
- Migrar gradualmente cinéticas detalladas restantes y pH-dependencias al builder con switches controlados.

## Ejemplos rápidos
Baseline estricto con diagnóstico:
```
python -m biorefinery.scripts.generate_unified_baseline --output unified.json --refresh --diagnose
```
ENMPC estable sin slack:
```
python -m biorefinery.scripts.run_enmpc \
  --total-time-h 12 --step-time-h 6 --horizon-time-h 12 \
  --nfe 2 --total-elements 10 --max-iterations 1 \
  --feas-prepass --output diag_no_slack.json --max-concentration 200 --min-hold-up 100
```

---
Última actualización: fase de factibilidad completada, slack mantenido solo como herramienta diagnóstica.
