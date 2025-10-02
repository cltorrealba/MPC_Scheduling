# Usage Guide (Sequential Workflow)

End-to-end practical steps to work with the biorefinery scheduling + MPC environment.

## 1. Instalación
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```
Opcional (sin extras dev):
```powershell
pip install -e .
```

## 2. Verificación Rápida
Ejecuta un baseline unificado mínimo:
```powershell
python -m biorefinery.scripts.generate_unified_baseline --output unified.json --feasible-seed --refresh
```
Revisa que `param_hash` aparezca y `status` sea consistente.

## 3. Modelo de Fermentación (Builder)
Uso básico:
```python
from biorefinery.models.fermentation import build_fermentation_model
m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                             initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1})
```
Activa rutas / descenso local:
```python
from biorefinery.models.fermentation import optimize_routes_local_descent
# evaluador ficticio minimiza rutas activas
res = optimize_routes_local_descent(m, lambda routes: (sum(routes.values()), True))
```

## 4. Escenarios (Declarativo)
Crea o modifica un JSON basado en `biorefinery/scenarios/example_basic.json` y carga:
```python
from biorefinery.models.scenario_loader import load_scenario
scn = load_scenario("biorefinery/scenarios/example_basic.json")
print(scn.fermentation.horizon_h, scn.scheduling.tasks[:1])
```
(Integración futura: `scenario_hash` incrustado en readiness.)

## 5. Readiness Multi-Horizonte
Evalúa estabilidad, baseline y adaptación NFE:
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --adaptive-nfe --strict-exit --regen-baseline
```
Salidas clave: `summary.json` (errores relativos, alertas, exit_code) y `fullscale_baseline.json` si regenerado.

Exit codes: 0 OK | 1 baseline | 2 param hash | 3 estabilidad | 4 fallback tier2 | 5 config freeze mismatch.

## 6. Pipeline Secuencial
Automatiza gates (baseline corta → reproducibilidad → medium → full):
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_pipeline.py --short-horizons 12,24 --medium-horizons 48 --full-horizons 72 --adaptive-nfe --strict
```
Resultados: `pipeline_summary.json`, `pipeline_report.md`.

## 7. ENMPC Loop
Ejemplo con prepass de factibilidad:
```powershell
python biorefinery/src/biorefinery/scripts/run_enmpc.py --total-time-h 12 --step-time-h 6 --horizon-time-h 12 --nfe 2 --max-iterations 2 --feas-prepass --output enmpc_run.json
```
Revisa métricas de drift y `max_mass_slack` (si usas `--mass-balance-slack`).

## 8. Rolling EMPC + Export
```powershell
python biorefinery/src/biorefinery/scripts/run_empc_rolling.py --horizon-h 24 --steps 5 --nfe 4 --output rolling.csv
```
Incluye columnas `final_<species>_pred` y métricas de deriva.

## 9. Métricas Económicas
Las funciones en `metrics/economic_aggregate.py` y `metrics/economic_extended.py` se aplican dentro de readiness / rolling para producir KPIs agregados; revisa su código para símbolos disponibles.

## 10. Benchmarks de Performance
```powershell
python -m biorefinery.scripts.benchmark_baseline --repeat 3 --output biorefinery/results/benchmark.json
```
Usa diferencias en `build_time_s` y `solve_time_s` para detectar regresiones.
Readiness añadirá (futuro) `adapt_trial_times` y speedup coarse/fine.

## 11. Config Freeze
Primera corrida congela flags:
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --adaptive-nfe --config-freeze --regen-baseline
```
Corrida posterior con cambios lanza exit code 5 bajo `--strict-exit`.

## 12. Limpieza y Snapshot
```powershell
python -m biorefinery.scripts.snapshot_results --pattern "summary.json" --output bundle.zip
python -m biorefinery.scripts.clean_outputs --older-than-days 7
```

## 13. Integración Scheduling + Control
Scripts `integrate_scheduling_enmpc.py` / `run_integrated.py` permiten experimentar acoplamiento; para iteraciones internas usar primero readiness y ENMPC aislado.

## 14. Extender Cinéticas
1. Añadir parámetros al builder.
2. Actualizar `compute_param_hash`.
3. Regenerar baseline (`--regen-baseline`).
4. Ejecutar readiness y revisar exit code (esperado 2 si hash cambió y baseline no se refrescó).

## 15. Buenas Prácticas
- Cambios pequeños y atómicos acompañados de baseline/regeneración documentada.
- Añadir test cuando se incorporen nuevos campos JSON de métricas.
- Mantener rutas discretas síncronas entre builder y adaptadores DSDA.

## 16. Tabla de Referencia Rápida
| Tarea | Script / Función | Artefacto |
|-------|------------------|-----------|
| Baseline determinista | generate_unified_baseline | unified.json |
| Readiness multi-horizonte | run_fullscale_readiness | summary.json |
| Pipeline completo | run_fullscale_pipeline | pipeline_summary.json |
| ENMPC loop | run_enmpc | enmpc_run.json |
| Rolling EMPC | run_empc_rolling | rolling.csv |
| Benchmark | benchmark_baseline | benchmark.json |
| Hash parámetros | compute_param_hash | param_hash string |
| Config freeze | run_fullscale_readiness --config-freeze | config_freeze.json |

## 17. Dónde Profundizar
- Arquitectura detallada: `ARCHITECTURE.md`
- Diccionario de funciones: `FUNCTION_REFERENCE.md`
- README: visión general y motivación.

## 18. Troubleshooting (Problemas Comunes)
| Síntoma | Causa Probable | Acción |
|---------|----------------|--------|
| Exit code 2 en readiness | Cambió un parámetro cinético (param_hash mismatch) | Regenerar baseline (`--regen-baseline`) y commitear artefacto |
| Exit code 5 | Flags congelados difieren (`config_freeze.json`) | Revisar diff, actualizar freeze (regenerar) o revertir cambio |
| Concentraciones infladas + M cerca del mínimo | Bounds poco restrictivos o falta de dilución | Ajustar `max_concentration`, revisar `include_dilution` y feeds |
| Slack de masa alto | Inconsistencia estructural o inicialización | Revisar inicializaciones, usar baseline factible y diagnosticar restricciones |
| Speedup adaptación < objetivo | Malla coarse demasiado similar a fine o sobrecarga solver | Aumentar `--adaptive-min-speedup` o aceptar fine; revisar nfe base |
| Drift persistente crítico | Tendencia real o mal dimensionado horizon | Ajustar horizonte, verificar cinéticas, revisar eventos externos |
| Diferencias grandes coarse vs fine | Tolerancia muy estricta o cambios cinéticos recientes | Revisar pesos `--adaptive-error-weights` y tolerancias, regenerar baseline |

### Recolección Rápida de Evidencia
Para abrir un issue interno captura: `summary.json`, `pipeline_summary.json`, fragmento de logs (últimas 50 líneas) y hash de commit.

### Placeholder scenario_hash
Una vez implementado `scenario_hash`, revisar que aparezca en baseline y summaries; si falta, ejecutar readiness con flags que incluyen escenario.

---
Actualiza esta guía cuando cambie el flujo recomendado o se añada un nuevo gate obligatorio.
