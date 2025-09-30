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
- Extracción modular de neighborhoods, evaluación, DSDA, solver fallback y reformulación externa.
- Logging centralizado (`biorefinery.logging_config`).
- Pruebas unitarias iniciales (neighborhoods, line search) bajo `tests/`.
- `extvars_gdp_to_mip` es actualmente un stub (passthrough) documentado en `docs/ARCHITECTURE.md`.
- Nuevo builder incremental de modelo de fermentación (`biorefinery.models.fermentation.build_fermentation_model`) para migrar gradualmente la lógica DAE.  
  *Flag `include_kinetics=True` añade parámetros cinéticos (rendimientos, qmax, constantes de inhibición, parámetros pH) y variables de tasas `q` (uptake) y `R` (pools de producción). `detailed_kinetics=True` activa expresiones completas (pH Gauss + inhibiciones cruzadas + reformulación log-exp para evitar derivadas singulares). Extensiones recientes: balances diferenciales ampliados (G, X, Eth, F, HMF, ACT, Cell, CO2), soporte de dilución (`include_dilution=True` + `feed_concentrations`), parámetro mutable `route_config`, helpers `set_route_activation`, `set_routes_activation`, `get_route_external_variables`, y wrapper `optimize_routes_local_descent` para búsquedas discretas ligeras. Todas las rutas desactivadas fuerzan exactamente `q=0` (sin residuos denormales) vía fijación explícita de variables y gating multiplicativo.*

## Ejecutar Pruebas
Después de instalar con extras de desarrollo:
```powershell
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

## Licencia y Origen
Este trabajo deriva de un repositorio académico original (créditos al autor original). Este fork se limita a reorganización y reproducibilidad.

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

Ejemplo rápido:
```python
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation

m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
               initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0,'ACT':0,'HMF':0})

set_route_activation(m,'G', False)
print('Ruta G activa?', m.route_config['G'].value)
set_route_activation(m,'G', True)
print('Ruta G activa?', m.route_config['G'].value)

print('Params qmax presentes:', [name for name,_ in m.component_map().items() if str(name).startswith('qmax_')])
```

### Mini ejemplo de exploración DSDA conceptual
```python
import pyomo.environ as pe
from biorefinery.models.fermentation import build_fermentation_model, set_route_activation

m = build_fermentation_model(include_kinetics=True, detailed_kinetics=True,
               initial_concentrations={'G':10,'X':5,'Eth':0,'Cell':1,'F':0,'ACT':0,'HMF':0})

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

