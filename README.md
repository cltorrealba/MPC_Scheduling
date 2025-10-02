# Biorefinery Scheduling & MPC (Subset Cleanup)

![CI](https://github.com/cltorrealba/MPC_Scheduling/actions/workflows/ci.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-codecov_pending-lightgrey)
_(La integración con Codecov está configurada en CI; el badge se actualizará tras el primer reporte exitoso.)_

Este fork reorganiza y limpia el subconjunto de interés del repositorio original para enfocarse en los modelos de fermentación, scheduling y control (MPC) de una biorefinería.

## Objetivo
Proveer una base clara y reproducible para:
- Construir el modelo (Pyomo + DAE + GDP cuando aplique)
- Ejecutar un caso de scheduling + dinámica + control MPC
- Extender con escenarios y análisis posteriores

## Estructura Actual (fase 1 de refactor)
```
biorefinery/
  src/biorefinery/
    models/            # (Futuro) Modelos modulares fermentación, hidrólisis, scheduling
    optimization/      # (Futuro) Métodos de solución, inicialización, estrategias GDP
    plotting/          # (Futuro) Funciones de graficación
  data/
    raw/               # CSV originales (copiados desde biorefinery_models)
  experiments/
    scenarios/         # Archivos JSON de condiciones iniciales + index.csv generado
  scripts/
    run_mpc.py         # Wrapper que ejecuta el script legado
  results/
    figures/           # Resultados gráficos
  docs/
requirements.txt       # Dependencias mínimas
biorefinery_models/    # Código original (legacy fuente de verdad temporal)
functions/             # Utilidades originales (se irá seleccionando lo necesario)
```

## Instalación
Recomendado: entorno virtual Python 3.9–3.11.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Si solo se desea el entorno mínimo sin extras de desarrollo:
```powershell
pip install -e .
```

## Ejecución Rápida (Temporal)
Mientras se completa la migración, el script original se ejecuta directamente:
```powershell
python biorefinery_models/Fermentation_Scheduling_and_MPC.py
```
Nota: Puede requerir solvers externos (ej. `ipopt`). Si no hay solver MINLP disponible se activa la cadena de fallback (intento GAMS->solver, luego solver directo, luego ipopt si continuo). 

### Fallback Multi-Solver
El proyecto incorpora ahora utilidades para seleccionar el primer solver disponible en un orden preferido. Orden por defecto:

1. Ipopt (NLP continuo, open source)
2. GAMS + CONOPT (si se dispone de licencia)
3. BONMIN (MINLP híbrido; requiere Ipopt internamente)
4. SCIP (MINLP)

El helper `pick_available_solver()` en `biorefinery.optimization.solvers` recorre esta lista y retorna el primero utilizable. La prueba de baseline registra el solver usado en el JSON para reproducibilidad; si se ejecuta con otro solver distinto se hace skip en lugar de fallar, permitiendo regenerar la baseline de forma explícita.

Ejemplo:
```python
from biorefinery.optimization.solvers import pick_available_solver
name, opts = pick_available_solver(return_options=True)
print('Usando solver:', name, 'opciones:', opts)
```

Para forzar GAMS + CONOPT establece variables de entorno de GAMS (PATH) y licencia válida, y asegúrate de que `SolverFactory('gams')` esté disponible. El test de baseline aplicará `solver.options['solver'] = 'conopt'` automáticamente bajo el modo gams.


Ejecución futura (interfaz modular prevista):
```powershell
python -m biorefinery.scripts.run_mpc --scenario base
```

## Estado del Refactor (Resumen)
Referencia detallada de objetivos y backlog: ver `biorefinery/docs/ROADMAP_FASE2.md`.

- Extracción modular de neighborhoods, evaluación, DSDA, solver fallback y reformulación externa.
- Logging centralizado (`biorefinery.logging_config`).
- Pruebas unitarias iniciales (neighborhoods, line search) bajo `tests/`.
- `extvars_gdp_to_mip` es actualmente un stub (passthrough) documentado en `docs/ARCHITECTURE.md`.
- Nuevo builder incremental de modelo de fermentación (`biorefinery.models.fermentation.build_fermentation_model`) para migrar gradualmente la lógica DAE.  
pytest
```
Para mayor detalle de cobertura:
```powershell
pytest --cov=biorefinery --cov-report=term-missing
```

## Readiness Runner: Adaptación NFE y Estabilidad (Novedades)
Se incorporó un script de verificación multi-horizonte `run_fullscale_readiness.py` que valida:

- Reproducibilidad vía baseline (`fullscale_baseline.json`) y `param_hash` de parámetros cinéticos.
- Selección adaptativa de discretización (NFE) comparando una malla fina vs una malla gruesa.
- Fallback multi-tier para robustez (tier0 normal, tier1 nfe-1, tier2 reducción de horizonte de predicción).
- Métricas de deriva (`drift_l2_mean`) y métricas económicas promedio para comparar vs baseline extendida.
- Alertas de estabilidad por concentración máxima, thresholds por especie y tendencia/persistencia de deriva.

### Adaptación NFE (Flags Clave)
| Flag | Descripción |
|------|-------------|
| `--adaptive-nfe` | Activa el modo adaptativo (coarse = nfe/2 vs fine = nfe base). |
| `--adaptive-nfe-rel-tol` | Tolerancia relativa base (escala inverso con el horizonte). |
| `--adaptive-nfe-min-tol` | Piso de tolerancia tras el escalado. |
| `--adaptive-error-weights` | Pesos para norma ponderada: `eth:1,hold:1,drift:0.5,econ:0.2`. |
| `--adaptive-min-speedup` | Mínimo speedup (fine/coarse) requerido para aceptar coarse. |

La aceptación de la malla coarse requiere (a) que el peor error relativo y (b) la norma ponderada estén <= tolerancia efectiva y (c) el speedup sea >= mínimo. Si (a)+(b) se cumplen pero (c) falla, se fuerza la malla fina (`adapt_reason = coarse_within_tol_low_speedup`).

Campos añadidos por horizonte (`HorizonResult`):
- `adapt_metrics`: difs relativas (`rel_eth`, `rel_hold_up`, `rel_drift`, `rel_econ`, `worst`, `error_norm`).
- `adapt_error_norm`: valor numérico de la norma ponderada.
- `adapt_trial_times`: tiempos de ejecución coarse/fine para análisis de speedup.
- `adapt_reason`: causa concreta de decisión.

### Fallback Avanzado
Se activa con `--advanced-fallback`. Si la corrida base falla:
1. Tier1: reintenta con `nfe-1` (si >2).
2. Tier2: reduce horizonte de predicción (`--fallback-pred-scale`, default 0.5). Si bajo `--strict-exit` y se usó tier2 (sin otras fallas) se retorna exit code 4 (alerta de degradación).

### Estabilidad y Alertas
| Flag | Función |
|------|---------|
| `--stability-max-conc-thresh` | Umbral sencillo para concentración final de etanol como proxy global. |
| `--stability-species-threshold` | Lista `Sp:valor,...` para marcar excedencias en columnas `final_<Sp>_pred`. |
| `--stability-drift-trend-threshold` | Pendiente mínima de tendencia de `drift_l2` (slope simple) para alertar. |
| `--stability-drift-trend-window` | Ventana usada en slope simple. |
| `--stability-drift-persist-window` | Longitud de cada sub-ventana para regresión LS de persistencia. |
| `--stability-drift-persist-count` | Cuántas ventanas consecutivas deben superar el threshold para `critical`.

Estructura de `stability_alerts`:
```json
{
  "alerts": {
    "max_concentration_exceeded": 6.7,
    "species_Eth_exceeded": {"value": 6.7, "threshold": 5.0},
    "drift_persist": {"slopes": [0.05, 0.06]}
  },
  "severity": "critical"
}
```
`severity` = `warning` si hay un único evento leve, `critical` si múltiples especies exceden, deriva persistente o combinación de eventos. Cuando hay cualquier alerta se marca `stability_ok = False` y bajo `--strict-exit` puede elevar el código (>=3) o 4 si sólo hubo fallback de tier2.

### Ejemplos
```powershell
# Adaptación con pesos y speedup mínimo
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --adaptive-nfe --adaptive-error-weights eth:1,hold:1,drift:0.3,econ:0.1 --adaptive-min-speedup 1.25 --regen-baseline

# Umbrales múltiples + deriva persistente
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 24 --adaptive-nfe --stability-species-threshold Eth:5,G:50 --stability-drift-trend-threshold 0.02 --stability-drift-persist-window 4 --stability-drift-persist-count 2

# Fallback estricto
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 48 --adaptive-nfe --advanced-fallback --strict-exit
```

### Interpretación de Exit Codes (strict)
| Código | Significado |
|--------|-------------|
| 0 | Todo OK (baseline dentro de tolerancia y sin alertas) |
| 1 | Desviaciones vs baseline fuera de tolerancia |
| 2 | `param_hash` mismatch (regenerar baseline) |
| 3 | Alertas de estabilidad (warning/critical) |
| 4 | Se necesitó fallback tier2 aunque sin otras fallas |
| 5 | Mismatch de configuración congelada (`--config-freeze`) |

La prioridad es incremental: si coexistieran se usa el máximo.

### Congelación de Configuración (Config Freeze)
Para garantizar reproducibilidad entre ejecuciones de readiness se puede activar:

| Flag | Descripción |
|------|-------------|
| `--config-freeze` | Habilita verificación de hash sobre un subconjunto de flags. |
| `--config-freeze-keys` | Lista de flags (nombres CLI) a incluir en el hash (default incluye horizontes, tolerancias y parámetros adaptativos). |

Funcionamiento:
1. Primera ejecución con `--config-freeze --regen-baseline` genera `config_freeze.json` con snapshot y hash.
2. Ejecuciones posteriores recomputan el hash; si difiere y `--strict-exit` está activo -> exit code 5.
3. El resumen (`summary.json`) incluye `config_freeze.mismatch` con hashes para auditoría.

Ejemplo:
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --adaptive-nfe --config-freeze --regen-baseline
# Cambiamos un flag congelado
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 24 --adaptive-nfe --config-freeze --strict-exit
```

Para extender la lista:
```powershell
--config-freeze-keys "horizons,step_h,pred_h,adaptive-nfe,adaptive-nfe-rel-tol,feedback"
```



## Logging
Por defecto nivel INFO a stdout. Para elevar a DEBUG:
```python
from biorefinery.logging_config import set_level
set_level("DEBUG")
```
O establecer variable de entorno antes de ejecutar (en PowerShell):
```powershell
$env:BIOREF_LOG_LEVEL = "DEBUG"; python biorefinery_models/Fermentation_Scheduling_and_MPC.py
```

## Configuración Centralizada
El módulo `biorefinery.config` unifica parámetros de ejecución:
- Solver NLP primario: `BIOREF_SOLVER_NLP` (default: ipopt)
- Solver MINLP primario: `BIOREF_SOLVER_MINLP` (default: bonmin)
- Time limit (segundos): `BIOREF_TIME_LIMIT` (default: 3600)
- Verbosidad solver (tee): `BIOREF_SOLVER_TEE` (0/1)

Uso rápido:
```python
from biorefinery.config import get_config
cfg = get_config()
print(cfg.primary_nlp, cfg.time_limit)
```

## Acceso a Datos
Usar el helper:
```python
from biorefinery.models.data_access import get_data_path
path = get_data_path("Glucose.csv")
```
Hace fallback automático a la ruta legacy si aún no se migró el archivo.

## Notas sobre Dependencias
Dependencias núcleo: Pyomo, NumPy, pandas, Matplotlib, SciPy. 
Extras de desarrollo: pytest + pytest-cov.
Solver recomendado para continuo: Ipopt (instalación externa no incluida). Para MINLP considerar integrar BONMIN/SCIP vía Pyomo o GAMS si licencia disponible.

---
_Si algo falla al correr el script original, documentar el error exacto y se añadirá sección de troubleshooting._

## Builder de Fermentación y Kinetics (Detalle)
El builder acepta `include_kinetics` (False por defecto) para mantener un modelo mínimo rápido en CI y pruebas unitarias. Con la opción activada:

- Params migradas: `Y_CO2_G`, `Y_CO2_X`, `Y_Eth_G`, `Y_Eth_X`, `Y_Cell_G`, `Y_Cell_X`, `Y_ACT_HMF`, `Y_CO2_HMF`, `qmax_*` (G, X, F, HMF, ATC), `KI_*`, `KIP_*`, `KSP_*`, `gamma_*`, mantenimiento (`m_G`, `m_X`), dependencia pH (`K0G/K1G/K2G`, `K0X/K1X/K2X`).
- Variables: `q[t,substrato]` (G, X, F, HMF, ACT) y `R[t,reaccion]` (Eth, ACT_from_HMF, CO2_total).
- Constraints stub: relaciones de rendimiento (ej. `R_Eth = q_G*Y_Eth_G + q_X*Y_Eth_X`). No se incluyen aún los términos de inhibición ni balances de concentración completos.

Novedades recientes:
- Balances de concentración (subset: G, X, Eth) enlazando derivadas con `q` y `R`.
- `initial_concentrations={}` para fijar valores iniciales reproducibles.
- `route_config` (Param mutable) y helper `set_route_activation` para toggles discretos.
 - `route_config` (Param mutable), helper `set_route_activation` y utilitario `get_route_external_variables`.

Roadmap cinético actualizado (resumido):
1. (Hecho) Parámetros + tasas base y constraints estequiométricos.
2. (Hecho) Cinética detallada glucosa & xilosa (inhibiciones + pH).
3. (Parcial) Cinética simplificada F, HMF, ACT (expr. detalladas futuras si se requieren).
4. (Hecho) Balances ODE ampliados + dilución opcional.
5. (Hecho) Toggles discretos y descenso local ligero DSDA.
6. (Pendiente) Validación cuantitativa vs script legado + escenarios de sensibilidad.

m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
               initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0,'ACT':0,'HMF':0})

print('Params qmax presentes:', [name for name,_ in m.component_map().items() if str(name).startswith('qmax_')])
```
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation
routes = ['G','X','F','HMF','ACT']
best = None
for r in routes:
  set_route_activation(m, r, False)
  # Aquí iría solve_subproblem(m) cuando el solver wrapper esté acoplado
  val = pe.value(m.obj)
  best = val if best is None else min(best, val)
  set_route_activation(m, r, True)
print('Mejor valor objetivo en vecinos simples:', best)
```

### Extracción de variables externas (DSDA)
### Dilución y alimentación
El builder ahora soporta `include_dilution=True` y un diccionario `feed_concentrations={"G":50.0, ...}`. Cuando se activa:
- Cada balance incluye término de salida: `-(F_total/M)*C_j`.
- Término de entrada: `+(F_total/M)*feed_conc[j]`.
- Si una especie no está en `feed_concentrations`, se asume 0.

Ejemplo rápido:
```python
m = build_fermentation_model(include_kinetics=True, include_dilution=True,
                             feed_concentrations={'G':40.0}, initial_concentrations={'G':5,'Cell':1})
```
```python
from biorefinery.models.fermentation import get_route_external_variables
ext_vars = get_route_external_variables(m)
print(ext_vars)  # {'route_active_G':1, ...}
```

### Adapter DSDA Ligero (`optimization/dsda_adapter.py`)
Se añadió un adaptador minimalista para búsquedas discretas sobre `route_config` sin invocar el enumerador completo `dsda_enumeration`.

Funciones clave:
- `extract_route_vector(model)` -> lista binaria del estado de rutas.
- `apply_route_vector(model, vector)` -> aplica vector (0/1) a `route_config`.
- `one_flip_neighbors(vector)` -> genera vecinos por flip único.
- `evaluate_vector(kwargs_builder, vector)` -> construye modelo, aplica vector y resuelve (devuelve `EvalResult`).
- `steepest_improvement_step(...)` -> un paso (evalúa todos los 1-flip y retorna el mejor si mejora).
- `run_local_descent(...)` -> aplica iterativamente pasos steepest hasta no mejorar o alcanzar `max_iters`.

Ejemplo rápido de descenso local:
```python
from biorefinery.optimization.dsda_adapter import run_local_descent

builder_kwargs = dict(
  include_kinetics=True,
  detailed_kinetics=False,
  initial_concentrations={'G':5,'X':2,'F':0.5,'HMF':0.2,'ACT':0.1,'Eth':0,'Cell':1,'CO2':0}
)
res = run_local_descent(builder_kwargs, start_vector=[1,1,1,1,1], max_iters=10)
print('Objetivo final:', res['incumbent'].objective)
print('Evaluados:', res['evaluated_count'], 'Cache hits:', res['cache_hits'])
```

Motivación: permitir pruebas rápidas y reproducibles en CI sin dependencias de GAMS o transformaciones GDP, antes de integrar el motor DSDA completo.

### Utilidades de Rutas y Descenso Local Conveniente

Para trabajar directamente sobre un modelo ya construido (sin reconstruir en cada evaluación) se añadieron helpers en `biorefinery.models.fermentation`:

Funciones clave:
- `set_route_activation(model, 'G', False)` fija/des fija una sola ruta (fija `q[t,'G']=0`).
- `set_routes_activation(model, {'G':0,'X':1,...})` toggles en bloque.
- `get_route_external_variables(model)` devuelve dict `{route_active_G:1,...}`.
- `optimize_routes_local_descent(model, evaluator, max_iters=20)` ejecuta vecino 1-flip iterativo usando el evaluador provisto.

El evaluador recibe un dict `{route_name:0/1}` y debe devolver `(objective_value, feasible_bool)`. Ejemplo minimalista sin resolver el modelo (pseudo objetivo = número de rutas activas):

```python
from biorefinery.models.fermentation import (
  build_fermentation_model, optimize_routes_local_descent
)

m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False,
                             initial_concentrations={'G':10,'X':5,'Cell':1})

def evaluator(route_state):
    # Asignar estados
    for r, val in route_state.items():
        m.route_config[r] = val
    # Pseudo objetivo: minimizar rutas activas
    obj = sum(route_state.values())
    return obj, True

res = optimize_routes_local_descent(m, evaluator, max_iters=5)
print('Mejor vector:', res['best_vector'])
print('Objetivo:', res['best_value'])
```

## ENMPC (Económico / NMPC) Herramientas y Reproducibilidad

Se añadieron scripts utilitarios y banderas para ejecutar, pausar, reanudar y post‑procesar corridas ENMPC reproducibles.

### Script principal
`biorefinery/src/biorefinery/scripts/run_enmpc.py`

Flags clave:

- `--total-time-h`, `--step-time-h`, `--horizon-time-h`: tiempos total, paso aplicado y horizonte de predicción.
- `--nfe`, `--total-elements`: granularidad de discretización.
- `--economic-objective` / `--economic-objective-exact`: objetivo económico (surrogado o simbólico exacto).
- `--constant-policy`: desactiva optimización (usa último control aplicado) para pruebas rápidas deterministas.
- `--disturbance-alpha`: ruido relativo multiplicativo en composiciones de alimentación (planificación).
- `--execution-disturbance-alpha`: ruido aplicado después de predecir para simular deriva (drift).
- `--force-nonzero-drift`: garantiza una deriva mínima cuando el estado previsto es todo cero y hay ruido de ejecución.
- `--drift-exclude-holdup`: excluye el `hold_up` del cálculo de métricas de drift.
- `--export-step-only`: comprime la trayectoria a puntos de frontera de cada paso (reduce tamaño JSON).
- `--no-rates`: omite series cinéticas `q_series` y `R_series` para reducir tamaño.
- `--hash-params`: incluye `param_hash` (SHA256 truncado de parámetros cinéticos clave) para asegurar reproducibilidad paramétrica.
- `--checkpoint-interval N`: escribe un checkpoint JSON (sin comprimir) cada N iteraciones.
- `--resume-from archivo.json`: reanuda una corrida previa (verifica `config_hash`).
- `--ignore-config-hash`: permite reanudar aunque haya divergencia de configuración (se desaconseja salvo uso experimental).
- `--max-iterations M`: limita cuántas iteraciones nuevas ejecutar (útil para dividir corridas largas en etapas).

Metadata añadida en `meta` del JSON:

| Campo | Descripción |
|-------|-------------|
| `config_hash` | Hash estable de parámetros de ejecución (config temporal). |
| `param_hash` | Hash de parámetros cinéticos seleccionados (`--hash-params`). |
| `code_commit` | `git rev-parse --short HEAD` si disponible. |
| `drift_definition` | Texto describiendo cómo se computó la deriva. |
| `compressed_applied` | `true` si se aplicó compresión (step only). |
| `export_step_only` | Flag original solicitado por el usuario. |
| `no_rates` | Indica si se omitieron series `q` y `R`. |

### Checkpoint & Resume
1. Ejecutar primera etapa: `python run_enmpc.py --total-time-h 120 --max-iterations 5 --output etapa1.json --checkpoint-interval 2`
2. Reanudar: `python run_enmpc.py --resume-from etapa1.json --max-iterations 5 --output etapa2.json`
3. Unir: ver script `merge_enmpc_runs.py`.

### Fusión y Compresión Post‑hoc
`biorefinery/src/biorefinery/scripts/merge_enmpc_runs.py`

Permite concatenar varios JSON (no comprimidos) que comparten `config_hash`:

## Rolling EMPC Avanzado (Scheduling + Fermentación Acoplados)

Script: `biorefinery/src/biorefinery/scripts/run_empc_rolling.py`

Este script ejecuta un bucle de control económico predictivo (EMPC) que en cada paso:
1. Resuelve un modelo integrado scheduling → fermentación para un horizonte de predicción.
2. Captura el estado aplicado a fracción `apply_h/prediction_h` (state intermedio) y/o estado final.
3. Calcula métricas económicas y de deriva (drift) entre estado aplicado predicho y estado “realizado” con perturbaciones.
4. Propaga el estado al siguiente paso según modo seleccionado (final, applied, realized o heurístico auto).
5. (Opcional) Retroalimenta inventario inicial del scheduling con el estado fermentación previo (feedback scheduling).

### Flags Clave Nuevas

| Flag | Descripción |
|------|-------------|
| `--propagation-mode {final,applied,realized}` | Selecciona el estado que se usa como condición inicial en el siguiente paso. |
| `--auto-propagation` + `--auto-drift-threshold` | Heurística: usa realized si la deriva L2 ≤ threshold; si no, usa final. |
| `--exec-disturbance-alpha` | Ruido multiplicativo aplicado para generar el estado realized (simula perturbación de ejecución). |
| `--drift-exclude-holdup` | Excluye el hold‑up `M` del cálculo de deriva. |
| `--warm-start-schedule` | Usa lotes (batches) previos como valores iniciales de scheduling. |
| `--fermentation-warm-start` | Inicializa puntos interiores de la discretización DAE con el estado final previo. |
| `--economic-lambda` | Penalización (# de batches no cero) en `economic_metric`. |
| `--economic-lambda2` | Penalización adicional (promedio tamaño de batch) en `economic_metric2`. |
| `--export-drift-species` | Exporta CSV con deriva por especie en cada paso. |
| `--schedule-horizon-mode {prediction,applied}` | Permite acortar horizonte de scheduling al horizonte aplicado. |
| `--feedback-scheduling-mode {none,ethanol,all_species}` | Retroalimentación de inventario inicial del scheduling a partir del estado previo de fermentación. |
| `--feedback-scheduling-scale` | Factor de escala al mapear concentraciones a inventario inicial. |
| `--drift-window N` | Tamaño de ventana para promedios móviles de deriva. |
| `--drift-alert-threshold X` | Genera columna booleana `drift_alert` si `drift_l2_avg > X`. |

### Columnas CSV Principales

| Columna | Descripción |
|---------|-------------|
| `prediction_h`, `apply_h` | Horizonte de predicción y horizonte efectivamente aplicado (paso MPC). |
| `propagation_mode` | Modo usado para propagar estado al siguiente paso. |
| `schedule_horizon_h`, `horizon_gap` | Horizonte empleado en scheduling y brecha vs predicción. |
| `final_ethanol_pred`, `ethanol_applied_pred` | Concentraciones de Etanol al final y en el punto aplicado. |
| `economic_metric` | (EtOH_applied/apply_h) − λ1 * (#batches). |
| `economic_metric2` | (EtOH_applied/apply_h) − λ1 * (#batches) − λ2 * (avg_batch_size). |
| `schedule_feasible_flag` | 1 si scheduling terminó en condición óptima. |
| `schedule_obj_value` | Valor objetivo del scheduling (si disponible). |
| `drift_l2`, `drift_max_abs` | Métricas de deriva instantánea paso a paso. |
| `drift_l2_avg`, `drift_max_abs_avg` | Promedios móviles (ventana `--drift-window`). |
| `drift_l2_cum`, `drift_max_abs_cum` | Acumulados desde el inicio. |
| `drift_alert` | 1 si promedio móvil excede umbral. |

### Métrica Económica Extendida

Se definieron dos métricas:

1. `economic_metric = ethanol_applied / apply_h - λ1 * nbatches`
2. `economic_metric2 = ethanol_applied / apply_h - λ1 * nbatches - λ2 * avg_batch_size`

Donde:
- `nbatches`: número de batches con valor absoluto > 1e-12.
- `avg_batch_size`: promedio de tamaños de batches no cero.
- `λ1 = --economic-lambda`, `λ2 = --economic-lambda2`.

### Deriva (Drift)

La deriva se calcula aplicando ruido multiplicativo `α` a cada concentración (si `< 500`) generando un estado realized. Métricas:
- `drift_l2 = ||C_realized - C_predicted||_2` (incluye hold‑up salvo `--drift-exclude-holdup`).
- `drift_max_abs = max_i |Δ_i|`.
- Promedios móviles y acumulados permiten monitoreo de tendencia.
- `drift_alert = 1` si `drift_l2_avg > threshold`.

### Retroalimentación Scheduling (Closed-Loop Inventories)

Con `--feedback-scheduling-mode` se modifica el inventario inicial del siguiente problema de scheduling a partir del estado fermentación propagado:
- `ethanol`: solo Etanol → inventario `F` (ejemplo simplificado).
- `all_species`: todas las especies compartidas (`G,X,ACT,HMF,F,Cell`).
Escalamiento vía `--feedback-scheduling-scale`.

El payload JSON por paso incluye `scheduling.initial_inventory_used` para trazabilidad.

### Export de Deriva por Especie

Si se activa `--export-drift-species`, se genera `drift_species_log.csv` con columnas: `step_index,mode,<species...>` y valores de `realizado - predicho`.

### Ejemplo de Ejecución

```powershell
python biorefinery/src/biorefinery/scripts/run_empc_rolling.py \`n  --total-horizon-h 12 --empc-step-h 3 --prediction-horizon-h 6 \`n  --nfe-per-h 0.5 --exec-disturbance-alpha 0.05 --auto-propagation \`n  --economic-lambda 0.1 --economic-lambda2 0.05 --drift-window 3 --drift-alert-threshold 0.5 \`n  --feedback-scheduling-mode all_species --feedback-scheduling-scale 0.5 --export-drift-species
```

### Buenas Prácticas

- Activar warm starts (`--warm-start-schedule` y `--fermentation-warm-start`) para reducir tiempo de solución en corridas largas.
- Usar `--auto-propagation` para adaptarse dinámicamente a la calidad predictiva (prefiere realized si la deriva es baja).
- Monitorear `drift_l2_avg` y `drift_alert` para diagnosticar degradación de fidelidad del modelo.
- Comparar `economic_metric` vs `economic_metric2` para evaluar sensibilidad a penalización de tamaño de lotes.

### Próximos Pasos Potenciales

- Incorporar retroalimentación sobre variables de decisión futuras (ajuste dinámico de horizonte de scheduling según deriva acumulada).
- Inclusión de costos energéticos y de recursos en `economic_metric2`.
- Reentrenamiento/ajuste de parámetros cinéticos en línea cuando `drift_alert` persiste.

## Full-Scale Readiness Runner

Script: `biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py`

Objetivo: ejecutar múltiples horizontes (p.ej. 12, 24, 48 h) con escalamiento de discretización y comparar KPIs (Etanol, Hold-up) contra una baseline tolerantizada (±5% por defecto).

Características:
- Pre‑chequeo corto sanity (4 h total, paso 1 h) antes de horizontes largos.
- Mapeo de nfe configurable (`--nfe-map 12:4,24:6,48:8`).
- Fallback: si un horizonte falla reintenta con nfe-1.
- Snapshot de configuración + hash reproducible.
- Comparación baseline con registro incremental (crea baseline si no existe o `--regen-baseline`).
- Métrica de escalabilidad aproximada: `elapsed_s / (horizon_h*3600)`.
- Retroalimentación scheduling y auto-propagation opcionales.

Uso básico (primera vez crea baseline):
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --auto --feedback all_species --disturb 0.05
```
Comparación posterior (no regenerar baseline):
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24 --auto --feedback all_species
```
Regenerar baseline explícitamente:
```powershell
python biorefinery/src/biorefinery/scripts/run_fullscale_readiness.py --horizons 12,24,48 --regen-baseline
```

Campos clave en `summary.json`:
| Campo | Descripción |
|-------|------------|
| `config_hash` | Hash de configuración congelada. |
| `results[]` | Lista de horizontes con métricas (ethanol_final, hold_up_final, drift_l2_mean, economic_mean). |
| `baseline.mode` | `baseline_created` o `baseline_compare`. |
| `baseline.issues[]` | Diferencias que superan tolerancia. |
| `scalability_ratio.mean_ratio` | Promedio de (tiempo/hora_simulada). |
| `READINESS` (stdout) | PASS / ATTENTION informativo. |

Recomendación de criterios “ready”: baseline sin issues, `stability_ok=True` en todos los horizontes, ratio de escalabilidad no creciendo abruptamente al aumentar horizonte.


```powershell
python biorefinery/src/biorefinery/scripts/merge_enmpc_runs.py etapa1.json etapa2.json --output merged.json
```

O con compresión final:

```powershell
python biorefinery/src/biorefinery/scripts/merge_enmpc_runs.py etapa1.json etapa2.json --output merged_step.json --compress
```

Si se cambiaron flags y difiere el hash se forzará error salvo `--allow-hash-mismatch`.

### Validación Estructural
`biorefinery/src/biorefinery/scripts/validate_enmpc.py`

Comprueba consistencia interna (longitudes, presencia de campos meta) y opcionalmente exige `config_hash`:

```powershell
python biorefinery/src/biorefinery/scripts/validate_enmpc.py merged.json --print-summary
```

### Exportación a CSV
`biorefinery/src/biorefinery/scripts/export_enmpc_csv.py`

Genera dos CSV: trayectorias y controles.

```powershell
python biorefinery/src/biorefinery/scripts/export_enmpc_csv.py merged.json --prefix resultados/run1 --include-rates
```

Produce:
- `resultados/run1_trajectory.csv`
- `resultados/run1_controls.csv`

### Flujo Recomendado Completo
1. Correr etapa(s) con checkpoints.
2. Reanudar hasta cubrir horizonte total.
3. Fusionar (`merge_enmpc_runs.py`).
4. Validar (`validate_enmpc.py`).
5. (Opcional) Comprimir o exportar CSV para análisis / plotting rápido.
6. Versionar JSON + CSV junto con commit (`code_commit`).

### Pruebas Automatizadas
Se añadieron tests:
- `test_enmpc_merge.py`: fusión y compresión.
- `test_enmpc_tools.py`: export y validación.
- Otros: resume, drift, meta/no-rates, hash guard.

Esto asegura que cualquier cambio futuro en el loop NMPC preserve reproducibilidad y formato estable.

## Inicio Fase 4 (Homologación & Integración Scheduling-Control)

Se inicia la Fase 4 con tres frentes fundacionales añadidos:

1. Regresión Legacy Inicial: prueba `tests/test_legacy_regression_equivalence.py` compara parámetros cinéticos clave entre el script legacy y el builder modular (tolerancia relativa 1e-3).
2. Interfaz Scheduling-Control (Scaffolding): módulo `biorefinery.integration.scheduling_control_interface` con dataclasses `FermentationStateSnapshot` y `SchedulingDemandProjection`, más helpers placeholder.
3. Pipeline CI Inicial: workflow `.github/workflows/ci.yml` ejecuta pytest en matriz 3.9–3.11 y emite resumen de cobertura.

Próximos pasos inmediatos:
- Extender equivalencia a trayectorias dinámicas y baseline combinado.
- Traducir snapshot -> demanda multi-período realista y mapear schedule -> feeds NMPC.
- Métrica económica agregada (productividad + cumplimiento demanda) + prueba.
- Badge de CI y cobertura en encabezado README.

Esto formaliza el arranque de la Fase 4 (homologación estructurada).

## Flujo Integrado (Scheduling -> Fermentación -> Métrica Económica)

Script demostrativo: `python -m biorefinery.scripts.run_integrated --print`

Pasos internos:
1. Resuelve un scheduling mínimo (batch único) y calcula cumplimiento de demanda.
2. Inyecta la producción como incremento en `Cin` (feed) del modelo de fermentación mediante `apply_schedule_to_feeds`.
3. (Opcional) Resuelve fermentación (desactivado con `--no-solve-fermentation`).
4. Calcula métrica económica agregada (rendimiento EtOH + cumplimiento demanda) usando `compute_economic_aggregate`.

Ejemplo rápido (sin resolver fermentación para velocidad):
```powershell
python -m biorefinery.scripts.run_integrated --no-solve-fermentation --print
```
Salida esperada (valores aproximados):
```
Integrated run result:
  Produced ethanol mass (proxy): <g>
  Demand fulfilled: 5.0
  Aggregate score: 0.xx
```

Pruebas asociadas:
- `test_run_integrated.py`: valida score dentro de [0,1].
- `test_schedule_to_feeds.py`: mapea producción ponderada (`rho_prod`).

Próximas extensiones:
- Iteración multi-etapa: scheduling -> fermentación -> re-scheduling.
- Sustitución de heurística feed por derivación de flujo dinámico.
- Métricas económicas extendidas (costos operativos, energía) y ponderaciones externas.

### Loop Iterativo (Prototipo)
Script: `python -m biorefinery.scripts.run_integrated_iterative --print`

Realiza N iteraciones heurísticas ajustando inventario y demanda. Cada iteración:
1. Scheduling con inventario actualizado.
2. Mapping producción -> `Cin` + posible ajuste de flujos (helper disponible: `adjust_feed_flows_in_fermentation`).
3. Fermentación breve (opcional solve) y snapshot.
4. Cálculo incremental de métrica económica.

### Métrica Económica Extendida
Módulo: `biorefinery.metrics.economic_extended`
Combina: score_base (yield + demanda) + penalización de costo y energía:
`score_ext = wb*base + wc*(1 - costo_norm) + we*(1 - energia_norm)`

Test asociados:
- `test_run_integrated_iterative.py`
- `test_economic_extended.py`
- `test_adjust_feed_flows.py`

### Comparación Legacy vs Nuevo (Series)
Pruebas para homología dinámica:
- `test_legacy_dynamic_equivalence.py`: compara concentraciones finales clave.
- `test_legacy_series_equivalence.py`: compara trayectorias `G`, `X`, `Eth` (tolerancias iniciales amplias).  
Variables de entorno para generar baseline:
```
$env:BIOREF_REFRESH_LEGACY_DYN_BASELINE=1
$env:BIOREF_REFRESH_LEGACY_SERIES_BASELINE=1
```
Luego re‑ejecutar `pytest` para validar contra los nuevos archivos generados.

### Baseline Unificado & Modos de Tolerancia (Nuevo)
Se consolidaron las baselines de equivalencia legacy en un único archivo JSON:

`tests/legacy_unified_baseline.json`

Secciones actuales:
- `dynamic_finals`: concentraciones finales (`G`, `X`, `Eth`, `Cell`).
- `series_concentrations`: series discretizadas de `G`, `X`, `Eth`.
- `series_rates` (opcional / inicial): series de tasas `q[...]` y `R[...]` detectadas heurísticamente.
 - `param_hash` (global): hash truncado (16 hex) de parámetros cinéticos/estequiométricos relevantes; si cambia y no se refresca baseline, las pruebas hacen skip preventivo.

Variables de entorno clave:
- `BIOREF_REFRESH_BASELINES=1`: Regenera (o crea) TODAS las secciones presentes en la corrida y hace `skip` de las pruebas tras escribir el archivo.
- `BIOREF_BASELINE_FILE=otra_ruta.json`: Cambia la ruta destino (útil para experimentar sin sobrescribir baseline principal).
- `BIOREF_TOLERANCE_MODE=strict|lenient`: Cambia el conjunto de tolerancias cargadas. Default: `lenient`.

Mapping de tolerancias (valor inicial; se podrá endurecer conforme mejore la paridad cinética):
- Dinámico (finales): lenient = abs 5e-2 / rel 5e-2; strict = abs 2e-2 / rel 2e-2.
- Series (concentraciones): lenient = abs 1e-1 / rel 8e-2; strict = abs 5e-2 / rel 5e-2.
- Series (tasas): lenient = abs 2e-1 / rel 1.0 (placeholder amplio); strict = abs 8e-2 / rel 6e-2.

Flujo típico:
```powershell
$env:BIOREF_REFRESH_BASELINES=1; pytest -k legacy_dynamic_equivalence -q  # genera secciones disponibles
$env:BIOREF_REFRESH_BASELINES=1; pytest -k legacy_series_equivalence -q   # añade/consolida series
$env:BIOREF_REFRESH_BASELINES=1; pytest -k legacy_rates_equivalence -q    # añade tasas (si se detectan)
Remove-Item Env:BIOREF_REFRESH_BASELINES
pytest -k legacy_equivalence -q  # Ejecuta sin regenerar
```

Script alternativo (batch) para generar baseline unificada sin ejecutar múltiples tests:
```powershell
python -m biorefinery.scripts.generate_unified_baseline --nfe 4 --nfe-dynamic 3 --refresh
```
Reescribe `tests/legacy_unified_baseline.json` con finales, series y tasas (solo modelo nuevo) y registra `param_hash`.

#### Nuevas Banderas de Generación Determinista (Feasible Seed & Fallback)
Para eliminar ruido de infeasibilidad (especialmente en CI o durante refactors) se añadieron banderas:

| Flag | Efecto | Uso Típico |
|------|--------|-----------|
| `--feasible-seed` | No invoca solver. Fija todas las concentraciones constantes (valor inicial) y pone `q=R=0`. `status=feasible_seed`. | Baseline puramente estructural para regression estable. |
| `--no-solver` | Alias de `--feasible-seed`. | Sintaxis alternativa corta. |
| `--fallback-if-infeasible` | Intenta solve normal; si cualquier modelo termina en estado infeasible reemplaza sus valores por el patrón semilla (constante) y marca `status=feasible_seed_fallback` y `solver=ipopt+fallback`. | Mantener valores “reales” cuando factible, degradando limpiamente si no. |

Ejemplos:
```powershell
# 1) Baseline determinista sin solver
python -m biorefinery.scripts.generate_unified_baseline --feasible-seed --refresh

# 2) Alias equivalente
python -m biorefinery.scripts.generate_unified_baseline --no-solver --refresh

# 3) Intentar solve y caer a semilla si es infeasible
python -m biorefinery.scripts.generate_unified_baseline --fallback-if-infeasible --refresh
```

Interpretación de `status` en secciones del JSON:
- `feasible_seed`: nunca se llamó al solver; datos triviales para paridad estructural.
- `feasible_seed_fallback`: se intentó solver pero la corrida resultó infeasible y se sustituyó por semilla.
- (otros valores: cadena de terminación del solver, p.ej. `optimal`, `locallyOptimal`, `infeasible`).

Razonamiento: separar la detección de divergencias de formulación (hash + estructura + dimensiones) de la validez numérica temporal del modelo mientras se completa la migración cinética. Una vez estabilizado, se puede migrar la baseline a resultados realmente optimizados quitando `--feasible-seed` y endureciendo tolerancias.

Validación adicional:
- Prueba (opcional, inicialmente skip) `test_derivative_consistency.py`: compara derivada finita de `C` vs aproximación simple a partir de `q`/`R` para detectar divergencias gruesas de formulación antes de endurecer tolerancias. Se habilitará cuando la migración cinética esté completa.

Pruebas relevantes:
- `test_legacy_dynamic_equivalence.py` (usa sección `dynamic_finals`).
- `test_legacy_series_equivalence.py` (usa `series_concentrations`).
- `test_legacy_rates_equivalence.py` (usa `series_rates`).

### Paridad Cinética Próxima (Roadmap Breve)
Objetivo: Reducir gradualmente tolerancias hasta niveles estrictos uniformes.
Pasos planeados:
1. Migrar expresiones completas de inhibición cruzada F/HMF sobre rutas de formación Eth/ACT.
2. Unificar dependencia de pH residual (si falta) en términos faltantes de `q_X` y reacciones secundarias.
3. Exponer explícitamente variables legacy de tasa (si difieren en nombre) para mapear 1:1 en lugar de heurística por prefijo.
4. Implementar test de derivada numérica (consistencia: balances vs q/R) para detectar divergencias estructurales sutiles.
5. Endurecer tolerancias: mover `series` a abs 2e-2 / rel 3e-2 tras pasos 1–3 completados y estabilidad confirmada (>3 corridas CI).

Indicadores de finalización:
- Ninguna especie excede tolerancia estricta en 3 ejecuciones CI consecutivas.
- Tasa de skip por solver diferente < 5% (preferencia estable por Ipopt).
- Hash estructural de parámetros invariable durante 1 semana de cambios de refactor relacionados.





### Enforzamiento Exacto de Cero en Rutas Desactivadas
Se eliminó la necesidad de restricciones tipo Big-M: ahora cada ecuación cinética es una igualdad `q = route_config * expr` y adicionalmente el helper fija/des fija la variable. Esto evita residuos numéricos (~1e-40) que antes rompían aserciones estrictas en pruebas.

### Búsqueda Mejorada: Caching, Tabu y Multi-Start
Se añadieron extensiones ligeras para intensificar y diversificar la búsqueda discreta:

- `optimize_routes_local_descent(..., cache=True)`: Memoiza vectores ya evaluados (clave = tupla ordenada) reduciendo solves repetidos.
- `tabu_length=N`: Mantiene una lista FIFO de los últimos N vectores aceptados para evitar ciclos cortos.
- `logger=<callable|logger>`: Se invoca en cada mejora con payload `{iteration,best_value,vector,evaluated_count,cache_hits}`.
- `optimize_routes_multi_start(..., starts=K, seed=...)`: Ejecuta varios descensos locales independientes (multi-start) y reporta el mejor global.

Ejemplo rápido multi-start:
```python
from biorefinery.models.fermentation import build_fermentation_model, optimize_routes_multi_start

m = build_fermentation_model(include_kinetics=True, detailed_kinetics=False)

def evaluator(state):
  # Minimizar número de rutas activas penalizando vector nulo
  active = sum(state.values())
  return (1e3 if active==0 else active, True)

res = optimize_routes_multi_start(m, evaluator, starts=5, max_iters=6, seed=123, tabu_length=2)
print('Mejor valor multi-start:', res['best_value'])
print('Vector global:', res['best_overall'])
```

Interpretación de métricas:
- `evaluated_count`: Número de evaluaciones “nuevas” (no cacheadas) durante un descenso.
- `cache_hits`: Cuántas veces se reutilizó un resultado guardado.
- `runs`: Lista de resultados individuales en multi-start (cada uno incluye `start_vector`).

Uso del logger (ejemplo simple):
```python
def simple_log(info):
  print('Iter', info['iteration'], 'val', info['best_value'], 'vec', info['vector'])

optimize_routes_local_descent(m, evaluator, logger=simple_log, max_iters=5)
```

## Baseline Numérica y Validación

Para asegurar estabilidad numérica del modelo de fermentación se mantiene un baseline JSON:

Archivo: `tests/validation_baseline_fermentation.json`
Contiene:
- `metrics`: valores finales clave (`obj`, concentraciones finales seleccionadas).
- `time`: puntos de tiempo físicos (horizonte actual escalado).
- `series`: trayectorias de especies (`G`, `X`, `Eth`, `Cell`, `CO2`).
- `solver`: solver usado para generarla.
- Tolerancias absolutas y relativas (finales y series) para comparación dual.
 - `q_series` (nuevo): tasas cinéticas específicas por especie en `kinetic_species` (si el modelo define `m.q`).
 - `R_series` (nuevo): tasas de reacción agregadas por entrada en `product_reactions` (si el modelo define `m.R`).
 - `param_hash` (nuevo): hash SHA256 determinista de parámetros cinéticos y de operación relevantes. Cambios estructurales en parámetros harán que el test haga skip con mensaje hasta regenerar baseline.

### Generar / Regenerar Baseline
Primera ejecución de la prueba:
```powershell
pytest -k validation_baseline -q
```
Si no existe baseline la crea y marca la prueba como skipped.

Para regenerar explícitamente:
```powershell
set BIOREF_REFRESH_BASELINE=1; pytest -k validation_baseline -q
```
o usar el script:
```powershell
python -m biorefinery.scripts.generate_baseline --force --solver ipopt
```
Para omitir la inclusión de series de tasas (si solo interesan concentraciones):
```powershell
python -m biorefinery.scripts.generate_baseline --force --no-rates
```

### Validación de Series
`test_validation_timeseries.py` compara punto a punto las trayectorias con tolerancias duales:
- Condición de aceptación: `diff <= abs_tol` OR `rel <= rel_tol`.

Las series de tasas (`q_series`, `R_series`) se validan estructuralmente (existencia y longitud). Puedes extender la validación numérica añadiendo una lógica análoga si se desea un control más estricto de la cinética.

### Ajuste de Tolerancias
Modificar en el baseline o en el script (`ABS_TOL_FINAL`, etc.). Para reducir falsos positivos usar tolerancias relativas más amplias y absolutas más estrictas.

### Cambio de Solver
Si el baseline se generó con un solver distinto al disponible actual, la prueba hará skip en lugar de fallar; regenerar si se acepta el nuevo solver como referencia.

### Hash de Parámetros (`param_hash`)
Si el hash almacenado difiere del calculado en la ejecución actual y no se ha definido `BIOREF_REFRESH_BASELINE=1`, la prueba hace `skip` indicando la discrepancia. Esto evita falsos fallos cuando se cambian deliberadamente parámetros. Para aceptar el nuevo estado:
```powershell
set BIOREF_REFRESH_BASELINE=1; pytest -k validation_baseline -q
```

## ENMPC (Economic Nonlinear MPC) Receding Horizon

Loop receding horizon parametrizable para control económico / maximización de etanol con comparación a política constante.

### Concepto
- Horizonte de predicción H (`--horizon-time-h`).
- Paso de aplicación Δ (`--step-time-h`), Δ ≤ H.
- Receding horizon: resuelve, aplica primera porción, avanza estado y repite.
- Objetivo: etanol (por defecto) o métrica económica proxy (`--economic-objective`).
- Perturbaciones en composiciones de alimentación (`--disturbance-alpha`).
- Warm start de controles: se reutiliza el último control aplicado como inicialización en iteraciones siguientes.

### Flags Clave
`--total-time-h`, `--horizon-time-h`, `--step-time-h`, `--nfe`, `--total-elements`, `--economic-objective`, `--constant-policy`, `--disturbance-alpha`, `--solver`, `--output`, `--tee`.

### Salida JSON
```
{
  "meta": { ... },
  "trajectory": {
     "time_s": [...],
     "species": {"G": [...], ...},
     "hold_up": [...],
     "q_series": {"G": [...], ...},          # exportado si cinética activa
     "R_series": {"Eth": [...], ...}         # exportado si cinética activa
  },
  "records": [
     {"iteration":0, "applied_control":{...}, "economic_metric":x,
      "neg_species":[], "ethanol_non_monotonic":false, ...}, ...]
}
```

### Nuevos Flags en Records
- `neg_species`: lista de especies con valores negativos detectados (tolerancia -1e-9) durante el intervalo aplicado.
- `ethanol_non_monotonic`: True si la serie de etanol en el intervalo presenta decrementos mayores a 1e-8.

### Ejecuciones Ejemplo
```powershell
python -m biorefinery.scripts.run_enmpc --total-time-h 72 --horizon-time-h 24 --step-time-h 6 \
  --nfe 6 --total-elements 72 --output enmpc_run.json

python -m biorefinery.scripts.run_enmpc --total-time-h 72 --horizon-time-h 24 --step-time-h 6 \
  --nfe 6 --total-elements 72 --constant-policy --output constant_run.json

python -m biorefinery.scripts.run_enmpc --total-time-h 72 --horizon-time-h 24 --step-time-h 6 \
  --nfe 6 --total-elements 72 --economic-objective --disturbance-alpha 0.05 --seed 2025 \
  --output enmpc_econ_dist.json
```

### Organización de Salidas (Carpetas de Resultados)
Para mantener el repositorio limpio evita dejar JSON/PNG/CSV en la raíz usando:

- `--results-dir` en `run_enmpc`: crea directorio y coloca `output` + checkpoints `*_ck_###.json` dentro.
- `--output-dir` en `plot_enmpc_overlay`: guarda PNG y CSV en la carpeta indicada.

Ejemplo:
```powershell
python -m biorefinery.scripts.run_enmpc --total-time-h 48 --horizon-time-h 12 --step-time-h 6 \
  --nfe 5 --warm-start --enforce-monotonic-m --results-dir results/exp01 --output run_exp01.json

python -m biorefinery.scripts.plot_enmpc_overlay --runs results/exp01/run_exp01.json \
  --species Eth,G --plot-holdup --normalize-hours --output-dir results/exp01/plots \
  --output overlay.png --export-csv overlay.csv
```
Checkpoints generados: `results/exp01/run_exp01_ck_001.json`, `..._ck_002.json`, etc.

Limpieza futura: se añadirá script `clean_outputs.py` para eliminar artefactos antiguos por patrón (JSON/CSV/PNG) con opción `--dry-run`.

#### Procedimiento Recomendado de Limpieza (3 pasos)
1. Mover artefactos sueltos a un directorio de staging:
  ```powershell
  $stamp = Get-Date -Format "yyyyMMdd_HHmm"
  $stage = "results/root_stage_$stamp"; New-Item -ItemType Directory -Path $stage | Out-Null
  Get-Item diag_*.json, overlay_*.png, overlay_*.csv -ErrorAction SilentlyContinue | Move-Item -Destination $stage
  ```
2. Generar snapshot reproducible (ZIP + MANIFEST):
  ```powershell
  python -m biorefinery.scripts.snapshot_results --inputs $stage --patterns *.json *.png *.csv \
    --relative-to results --output snapshots/root_stage_$stamp.zip
  ```
3. Verificar y eliminar staging si el ZIP es válido:
  ```powershell
  Remove-Item -Recurse -Force $stage
  ```
Posteriormente usar `clean_outputs.py` con `--keep-latest` para rotación automatizada.

### Plots Comparativos
```powershell
python -m biorefinery.scripts.plot_enmpc_vs_constant --enm enmpc_run.json --const constant_run.json --prefix figs_enmpc
```
Genera: concentraciones, hold-up, controles, métrica económica.

### Tests
- `test_enmpc_basic.py`: estructura, divergencia control vs constante.
- `test_enmpc_economic.py`: objetivo económico + presencia q_series / R_series.
- `test_enmpc_drift.py`: métricas de drift bajo perturbación de ejecución.
- `test_enmpc_resume.py`: flujo parcial y reanudación incremental.

### Checkpoints, Resume y Estados Pred/Real (Novedad)
El runner `run_enmpc` ahora soporta resiliencia y análisis de discrepancias entre predicción y realización:

Flags nuevos:
- `--checkpoint-interval N`  Escribe el JSON (sin compresión) cada N iteraciones. Útil para ejecuciones largas o entornos inestables.
- `--resume-from archivo.json`  Reanuda una corrida previa (debe provenir de salida no comprimida). Reconstruye las series y continúa agregando iteraciones.
- `--max-iterations M`  Limita el número de iteraciones nuevas (ideal para dividir la corrida en segmentos). Si no se especifica, ejecuta todas las restantes.
- `--execution-disturbance-alpha a`  Aplica una perturbación aleatoria post-predicción a los estados al final del paso simulando discrepancias de ejecución.
- `--export-step-only`  (Ya existente) ahora se aplica solo al final; las corridas intermedias para reanudación deben permanecer sin compresión.
- `--no-rates`  Omite la exportación de `q_series` y `R_series` (ahorra tamaño si solo importan concentraciones).
- `--force-nonzero-drift`  Cuando el estado predicho es todo ceros y existe `--execution-disturbance-alpha`, asegura una deriva mínima para evitar métricas triviales.
- `--ignore-config-hash`  Permite reanudar aunque cambien parámetros clave (normalmente bloqueado para reproducibilidad).
- `--drift-exclude-holdup`  Excluye el término de hold-up del cálculo de drift.

Cada `record` incluye ahora:
- `predicted_end_state`: estado al final del paso según el modelo antes de perturbaciones (dict `{C: {sp: valor}, M: hold_up}`).
- `realized_end_state`: estado luego de aplicar perturbación de ejecución.
- `drift_l2`, `drift_max_abs`: métricas de desviación entre predicho y realizado (si `--execution-disturbance-alpha > 0`).

Metadatos ampliados:
```
"compressed_applied": true/false,
"checkpoint_interval": N | 0,
"resume_source": "archivo.json" | null,
"max_iterations": M | null
"no_rates": true/false,
"force_nonzero_drift": true/false,
"drift_definition": "l2 and max abs over species + hold_up (pred vs realized after exec disturbance)",
"config_hash": "<hash16>"   # SHA256 truncado de configuración relevante para detectar incompatibilidades de resume
"code_commit": "<git short hash>" | null
```

Guard de reanudación:
Al reanudar se compara `config_hash`; si difiere se aborta con error salvo que se pase `--ignore-config-hash`. Esto evita mezclar segmentos con configuración incompatible (p.ej. cambio de horizonte o activación de `--no-rates`).

Exclusión de hold-up en drift:
Con `--drift-exclude-holdup` las métricas se calculan solo sobre concentraciones de especies.

Ejemplo de corrida segmentada y reanudación:
```powershell
# Primera iteración únicamente
python -m biorefinery.scripts.run_enmpc --total-time-h 24 --horizon-time-h 12 --step-time-h 6 \
  --nfe 3 --total-elements 24 --max-iterations 1 --output parcial.json

# Reanudar hasta completar (resto de iteraciones)
python -m biorefinery.scripts.run_enmpc --total-time-h 24 --horizon-time-h 12 --step-time-h 6 \
  --nfe 3 --total-elements 24 --resume-from parcial.json --output completo.json

# Generar versión comprimida (endpoints) una vez finalizado
python -m biorefinery.scripts.run_enmpc --total-time-h 24 --horizon-time-h 12 --step-time-h 6 \
  --nfe 3 --total-elements 24 --resume-from completo.json --export-step-only --output completo_compacto.json
```

Buenas prácticas:
- Evitar usar `--export-step-only` en la corrida que se piensa reanudar (imposibilita resume).
- Guardar logs de solver si se hace `--tee` para análisis de convergencia entre segmentos.
- Fijar `--seed` para reproducibilidad completa de perturbaciones.

La prueba `test_enmpc_resume.py` valida esta funcionalidad end-to-end.

### Rolling EMPC (Scheduling→Fermentación Prototype)
Se añadió un prototipo ligero de loop rolling (separado del runner ENMPC completo) para encadenar resoluciones de un horizonte de predicción más largo que el paso aplicado, reutilizando el estado final como condición inicial del siguiente paso.

Script: `biorefinery/src/biorefinery/scripts/run_empc_rolling.py`

Uso básico:
```powershell
python biorefinery/src/biorefinery/scripts/run_empc_rolling.py ^
  --total-horizon-h 12 --empc-step-h 3 --prediction-horizon-h 6 ^
  --nfe-per-h 0.5 --store-json --log-dir logs/empc_rolling
```

Conceptos:
- `prediction-horizon-h (H)`: Ventana de optimización (programación mínima + fermentación) para cada solve.
- `empc-step-h (Δ)`: Porción aplicada antes de “receder” el horizonte. Se impone Δ ≤ H.
- `total-horizon-h`: Tiempo total acumulado a cubrir (el loop termina cuando se alcanza o excede).
- `nfe-per-h`: Densidad de discretización → `nfe = ceil(H * nfe_per_h)`.
- `schedule-horizon-mode`: Si `prediction` (default) la horizon de scheduling = H; si `applied` solo cubre Δ (acelera solves cuando scheduling es caro).

Flags nuevos / clave:
- `--warm-start-schedule`: Reutiliza lotes (B) del solve anterior como initial values.
- `--schedule-horizon-mode {prediction|applied}`: Ajusta duración del sub-problema de scheduling.
- `--exec-disturbance-alpha a`: Aplica perturbación pseudo-aleatoria a estado aplicado para métricas de drift.
- `--drift-exclude-holdup`: Excluye `M` del cálculo de drift.
- `--seed`: Semilla reproducible para ruido de ejecución.
- `--propagation-mode {final|applied|realized}`:
  - `final`: (default) Propaga el estado al final de H.
  - `applied`: Propaga el estado en el punto aplicado (Δ/H) sin disturbio.
  - `realized`: Propaga el estado aplicado perturbado (closed-loop simple con ruido de ejecución).
  - Usar con `--auto-propagation` para elegir dinámicamente entre `realized` y `final` según drift.
- `--auto-propagation` + `--auto-drift-threshold`: Selección heurística basada en L2 drift.
- `--fermentation-warm-start`: Inicializa nodos internos de la fermentación con el estado propagado anterior.
- `--economic-lambda λ`: Añade métrica económica `economic_metric = ethanol_applied/Δ - λ * (#batches != 0)`.
- `--export-drift-species`: Genera `drift_species_log.csv` con drift por especie (pred vs realized) por paso.
- Columnas nuevas: `schedule_horizon_h`, `horizon_gap`, `economic_metric`.

Salidas:
1. CSV `rolling_performance_log.csv` columnas:
  `step_index,t_start_h,t_end_h,prediction_h,apply_h,nfe,mod_elapsed_s,predicted_end_h,applied_abs_time_h,final_ethanol_pred,ethanol_applied_pred,final_hold_up_pred,hold_up_applied_pred,productivity_pred,git_commit,git_dirty,python_version,feasible_flag,drift_l2,drift_max_abs`.
  - `predicted_end_h`: fin absoluto del horizonte de predicción.
  - `applied_abs_time_h`: tiempo absoluto (h) del punto aplicado (fracción Δ/H de la predicción).
  - `ethanol_applied_pred` / `hold_up_applied_pred`: valores pronosticados al corte aplicado (antes de continuar hasta H).
  - `drift_l2`, `drift_max_abs`: métricas de desviación entre estado aplicado pronosticado y estado perturbado (si `--exec-disturbance-alpha>0`).
2. (Opcional `--store-json`) archivos `steps/step_XXX.json` con payload completo + `final_state` (concentraciones y hold-up) usado como handoff.

Handoff de estado:
- Cada iteración extrae estado aplicado (fracción Δ/H) y estado final; actualmente la propagación usa el estado final (política zero‑order hold) pero ya se expone `applied_state` para futura diferenciación.
- `applied_state` incluye `tau_selected` (punto de discretización cercano) y `abs_time_h`.

Limitaciones actuales / Próximas extensiones:
- Propagación aún basada en estado final; siguiente paso: opción para propagar estado aplicado.
- Modo `realized` actualmente no retroalimenta error en scheduling (solo en condiciones iniciales de fermentación).
- No se hace warm start de duales / estructura Pyomo (solo valores de B en scheduling).
- Disturbio aplicado no retroalimenta todavía a la predicción siguiente (sería modo closed-loop con error de seguimiento).
- Posible integración con métrica económica y control de alimentación variable.

Razón de coexistencia con `run_enmpc`:
> Este prototipo valida la tubería Scheduling→Cin→Fermentación en modo receding antes de integrar objetivos económicos y control de alimentación detallado del loop ENMPC principal.

Regeneración / limpieza:
```powershell
Remove-Item -Recurse -Force logs/empc_rolling
python biorefinery/src/biorefinery/scripts/run_empc_rolling.py --total-horizon-h 9 --empc-step-h 3 --prediction-horizon-h 6 --nfe-per-h 0.5 --log-dir logs/empc_rolling
```

Pruebas futuras sugeridas:
- Smoke test: ejecutar 2 pasos y validar monotonicidad de `t_start_h` y propagación de `Eth`.
- Test de handoff: verificar continuidad (diferencia pequeña entre estado inicial de paso k y final del paso k-1 para especies no consumidas drásticamente).
- Validación: CSV contenga exactamente `total_steps = ceil(total_horizon_h / empc_step_h)` filas (última puede truncar si Δ no divide exacto).

Sección sujeta a expansión conforme el prototipo se fusione con funciones de drift y objetivos económicos del runner ENMPC.

### Roadmap ENMPC
- Mejora warm start (inicializar también derivadas y estado dual).
- Serializar estimaciones pronóstico vs aplicado para cálculo de drift cuantitativo.
- Multi-variable control + objetivos compuestos (p. ej. productividad + costo feed).
- Integración DSDA intra-horizonte para decisiones discretas dinámicas.

### Mejoras Recientes ENMPC (Extendidas)
Nuevos flags en `run_enmpc`:
- `--economic-objective-exact`: activa objetivo económico simbólico exacto (implica `--economic-objective`).
- `--execution-disturbance-alpha`: factor de perturbación aplicado después de la predicción para simular desalineación (genera métricas de drift).
- `--export-step-only`: comprime la trayectoria exportando solo estado inicial y puntos al final de cada paso Δ.
- `--seed`: semilla para reproducibilidad de perturbaciones (feed y ejecución).

Campos nuevos en `meta`:
- `economic_objective_exact`, `execution_disturbance_alpha`, `export_step_only`, `seed`.

Campos nuevos por `record`:
- `drift_l2`: norma L2 de diferencia entre estado predicho y realizado (si hay perturbación de ejecución).
- `drift_max_abs`: máximo absoluto de diferencias especie a especie.

Compresión de trayectoria (`--export-step-only`): reduce tamaño del JSON para corridas largas manteniendo puntos relevantes para análisis de control.

Tests añadidos:
- `test_enmpc_economic.py`: objetivo económico exacto/surrogate y series cinéticas.
- `test_enmpc_drift.py`: valida que las métricas de drift sean positivas bajo perturbación.

## Fase 3: Estabilización Numérica, DSDA Multi-Start Persistente y Visualización Avanzada

Esta fase consolida tres ejes: (1) estabilización/diagnóstico de infeasibilidad en ENMPC, (2) exploración discreta multi-start persistente (DSDA) y (3) overlay de múltiples corridas con instrumentación completa.

### 1. Estabilización y Diagnóstico
Problema original: infeasibilidad recurrente dominada por la restricción de balance de masa (violaciones ~O(10^3)) y colapso de `M` a valores cercanos a cero, generando trayectorias degeneradas.

Medidas implementadas:
- Eliminación de balances duplicados que sobre-restringían el sistema.
- Parámetros configurables de cotas: `--max-concentration`, `--min-hold-up` para prevenir degeneración.
- Opción `--mass-balance-slack` con penalización cuadrática (`--mass-balance-slack-weight`) para cuantificar violaciones potenciales (diagnóstico sin abortar la corrida).
- Sufijo de escalado selectivo sobre variables clave (`q`, `R`, `M`, `C`) para mejorar condición numérica (sin alterar solución, ver test de invariancia `test_scaling_invariance.py`).
- Clamp de micro-negativos numéricos en variables no negativas al capturar warm start para evitar warnings y propagación de ruido.
- Flag opcional `--enforce-monotonic-m` agregando restricciones `M[t_i] ≥ M[t_{i-1}] - 1e-9` evitando descensos espurios lineales y negativos por drift numérico.

Diagnósticos disponibles por `record`:
- `max_constraint_violation`, `top_constraint_violations` (primeras 5 con magnitud).
- `avg_Fin`, `delta_M`, `min_M_over_horizon` (nueva métrica para monitorear estabilidad del hold-up dentro del sub-horizonte aplicado).
- `neg_species`, `ethanol_non_monotonic` para depurar trayectorias.

### 2. DSDA Multi-Start Persistente
Se añadió un script multi-start que:
- Explora configuraciones discretas de rutas (bitmask / toggles) mediante arranque aleatorio y/o enumeración parcial.
- Mantiene un cache JSON incremental (evita reevaluar combinaciones previas, conserva mejor global entre ejecuciones). 
- Expone hashing de configuración para invalidar cache cuando cambian parámetros relevantes.
- Está cubierto por prueba `test_dsda_cache.py` que verifica crecimiento del cache y selección del mejor.

Características clave:
- Reanudación natural: al relanzar el script sobre el mismo archivo de cache amplía el conjunto evaluado.
- Control sobre exhaustividad vs aleatoriedad (flags en el script DSDA). 
- Métricas por configuración: valor objetivo, factibilidad, timestamp.

### 3. Overlay Avanzado de Corridas ENMPC
Script: `biorefinery/scripts/plot_enmpc_overlay.py` ampliado con:
- Selección de especies y tasas (`--plot-rates` G,Eth,...).
- Panel opcional de hold-up (`--plot-holdup`).
- Panel de controles con serie completa reconstruida (`control_series`).
- Exportación CSV unificada (`--export-csv`) con esquema largo (`run,time,value,type,name`).
- Filtros por substring de nombre de run (`--filter-run-contains`, `--filter-run-exclude`).
- Modo columnas por corrida (`--per-run-columns`) para comparar 1:1 monotónico vs no monotónico.
- Detección de monotonicidad (`--monotonic-style-hint`): estilo sólido si `meta.enforce_monotonic_m=true`, estilo discontínuo si no.
- Anotación de estadísticas de hold-up (`--annotate-stats`) min/max/final.

Ejemplo comparativo:
```powershell
python -m biorefinery.scripts.run_enmpc --total-time-h 48 --step-time-h 6 --horizon-time-h 12 ^
  --nfe 5 --warm-start --enforce-monotonic-m --output diag_monotonic.json
python -m biorefinery.scripts.run_enmpc --total-time-h 48 --step-time-h 6 --horizon-time-h 12 ^
  --nfe 5 --warm-start --output diag_nomono.json
python -m biorefinery.scripts.plot_enmpc_overlay --runs diag_monotonic.json diag_nomono.json ^
  --species Eth,G --normalize-hours --plot-holdup --plot-controls ^
  --per-run-columns --monotonic-style-hint --annotate-stats --output overlay_columns.png
```

### Campos Nuevos en JSON (Fase 3)
- `trajectory.control_series`: dict con series de `F_liquified_fibers` y `F_C5liquid` a lo largo del horizonte aplicado.
- `records[*].min_M_over_horizon`: mínimo de M en puntos del sub-horizonte (sanity check de estabilidad).
- `meta.rate_scale`: factor de escala conceptual (afecta hashing, no debe cambiar solución física; test invariancia verifica).
- `meta.constant_hold_up`, `meta.mass_balance_slack`, `meta.mass_balance_slack_weight` y `meta.warm_start_iterations` consolidados.

### Nuevos Flags (Resumen rápido)
| Flag | Propósito |
|------|-----------|
| `--max-concentration` | Cota superior unificada para C[j]. |
| `--min-hold-up` | Cota inferior M para evitar colapso. |
| `--rate-scale` | Escalado de variables cinéticas para conditioning. |
| `--mass-balance-slack` | Activa reformulación con slack_M diagnóstica. |
| `--mass-balance-slack-weight` | Peso cuadrático penalización slack. |
| `--enforce-monotonic-m` | Monotonía no decreciente de M(t). |
| `--warm-start` | Aplica snapshot primal anterior para acelerar convergencia. |
| `--feas-prepass` | Pre-pase factibilidad con q,R=0 antes de liberar optimización. |

### Pruebas Añadidas (Fase 3)
- `test_scaling_invariance.py`: confirma invariancia de solución ante `--rate-scale`.
- `test_bounds_parameters.py`: verifica aplicación de bounds configurables.
- `test_dsda_cache.py`: crecimiento y consistencia del cache multi-start DSDA.

### Recomendaciones Operativas
- Para diagnósticos de infeasibilidad inicial: usar `--mass-balance-slack --tee` y revisar `top_constraint_violations`.
- Para producción estable: usar `--enforce-monotonic-m --min-hold-up <valor>` y evitar slack salvo necesidad.
- Limitar tamaño JSON en corridas largas con `--export-step-only` (solo después de finalizar si se planea resume intermedio).
- Activar `--hash-params` en estudios sensibles a cambios de cinética/parametría para versión controlada del baseline.

### Próximos Pasos (Futuro Post-Fase 3)
1. Penalización suave de variación en M (si se requieren trayectorias aún más suaves sin fijar monotonicidad estricta).
2. Integrar decisiones discretas dentro del horizonte NMPC (híbrido DSDA+NMPC).
3. Métrica económica ampliada (costos dinámicos de feed, penalizaciones de energía). 
4. Dashboard interactivo (streamlit o panel) para inspección multi-run sin regenerar PNG.

---
_Cierre Fase 3_: El sistema ahora ofrece un pipeline reproducible, con tooling para aislar problemas numéricos, comparar variantes estructurales y visualizar evoluciones bajo distintas políticas y estabilizadores.

## Herramientas de Mantenimiento y Empaquetado

### Limpieza de Artefactos (`clean_outputs.py`)
Permite suprimir o comprimir (a `.gz`) salidas antiguas filtrando por patrones, edad y conservando los N más recientes.

Ejemplos:
```powershell
# Simular (dry-run) qué PNG/CSV viejos (>7 días) se eliminarían
python -m biorefinery.scripts.clean_outputs --paths results --patterns *.png *.csv --older-than-days 7 --dry-run

# Comprimir JSON antiguos manteniendo los 3 más recientes
python -m biorefinery.scripts.clean_outputs --paths results --patterns *.json --older-than-days 2 --action compress --keep-latest 3
```
Flags claves:
- `--action delete|compress`
- `--keep-latest N` preserva N más nuevos
- `--hash-manifest` imprime hash SHA256 de la lista candidata
- `--older-than-days D` filtra por antigüedad

### Snapshot Reproducible (`snapshot_results.py`)
Empaqueta archivos (JSON/CSV/PNG) en un ZIP con `MANIFEST.json` (ruta relativa, sha256, size y `manifest_hash`).

```powershell
python -m biorefinery.scripts.snapshot_results --inputs results/exp01 --patterns *.json *.png *.csv ^
  --relative-to results --output snapshots/exp01_snapshot.zip
```
Usar `--dry-run` para inspeccionar antes de crear el archivo.

