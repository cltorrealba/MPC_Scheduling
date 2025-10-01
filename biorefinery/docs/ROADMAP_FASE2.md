# ROADMAP_FASE2

Estado final de la Fase 2 y pasos siguientes priorizados.

## Objetivos Clave (Fase 2)
1. Reproducibilidad fuerte: hashes (`config_hash`, `param_hash`), escenarios JSON, seeds.
2. Modularidad: API `FermentationConfig`/`build_fermentation_model_v2`, scheduling mínimo desacoplado.
3. Observabilidad y tooling: plotting rápido, benchmark baseline, validadores y merge.
4. CI robusto: capa rápida + matriz extendida.

## Entregables Completados
- API V2 fermentación (dataclasses + hash cinético).
- Corrección inhibición HMF y test dedicado.
- Wrapper DSDA minimal (`dsda_minimal`) + smoke test.
- Guard paramétrico en resume ENMPC (`--hash-params` + enforcement).
- Escenarios: schema + loader + ejemplo y doc.
- Scheduling mínimo: batch único/periodo, inventarios y capacidad.
- Benchmark básico (build/solve + memoria opcional).
- Plot rápido ENMPC (`plot_enmpc_quick.py`).
- CI reforzado (fast + extended).

## Definición de “Done” Fase 2
- Todos los scripts de tooling (run, merge, validate, export, plot, benchmark) ejecutables sin legacy directo.
- Tests cubren: hashing, resume, escenarios, scheduling stub, plotting, DSDA minimal, cinética clave.
- Un escenario ejemplo reproducible genera siempre el mismo `param_hash` con cinética activa.
- CI verde en Python 3.9–3.11 sin dependencias propietarias.

## Riesgos / Limitaciones Actuales
| Riesgo | Mitigación Planeada |
|--------|----------------------|
| Falta de validación cuantitativa completa vs legacy dinámico | Añadir test de regresión numérica multi-especies (Fase 3) |
| Scheduling sin tiempos de proceso multi-periodo | Extensión con duración y shift de inventario (similar a legacy GDP) |
| Ausencia de hash de escenario integrado en outputs | Incorporar `scenario_hash` (schema + contenido ordenado) en meta ENMPC |
| Performance solve variable (Ipopt) | Registrar stats en benchmark y fijar tolerancias solver para estabilidad |
| No cobertura Windows CI | Añadir job matrix Windows tras estabilizar dependencias |

## Backlog Priorizado (Para Fase 3)
1. `scenario_hash` + verificación en resume.
2. Duraciones en scheduling (introducir `processing_slots` y shift constraints).
3. Integración escenarios -> benchmark (`--scenario` flag) y reporte enriquecido.
4. Test de regresión numérica multi-especies (baseline ampliado + tolerancias adaptativas).
5. Extensión plotting: overlay de múltiples corridas y export PDF.
6. Hook de performance en CI (comparar tiempos vs JSON baseline con tolerancia configurable).
7. Warm start ENMPC (reutilizar valores previos de variables y duales).
8. Multi-start automático DSDA + caching persistente.
9. Generación de documentación API automatizada (sphinx/markdown export simple).

## Métricas de Calidad Propuestas
| Métrica | Objetivo Inicial |
|---------|------------------|
| Cobertura pruebas (líneas núcleo modelos + scripts) | >= 60% (subir a 75% Fase 3) |
| Tiempo job `fast` CI | < 60 s |
| Desviación param_hash en builds iguales | 0% (cualquier cambio => alerta) |
| Variación build_time_s benchmark entre commits consecutivos | < 10% |

## Criterios para Cierre de Fase 3 (visión preliminar)
- Scheduling soporta duraciones > 1 periodo y demandas múltiples.
- `scenario_hash` integrado en meta y validadores.
- Baseline cinético ampliado validado y versionado.
- Hook de regresión de performance operativo.
- Documentación sintetiza API pública y flujo reproducible end-to-end.

## Guía de Contribución Breve
- Añadir test al introducir cualquier nuevo campo en JSON outputs.
- Mantener pure data classes inmutables; si un test necesita mutar, reconstruir instancia.
- Evitar dependencias pesadas fuera de extras `dev`.
- Registrar cambios significativos en este roadmap antes de merge.

---
Última actualización: (auto) Fase 2 completada.
