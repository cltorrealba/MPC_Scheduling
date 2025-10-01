# Biorefinery Scheduling & MPC (Subset Cleanup)

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

