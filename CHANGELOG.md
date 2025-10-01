# Changelog

## [0.3.0] - Fase 3 (2025-10-01)
### Added
- ENMPC stabilización: bounds configurables (`--max-concentration`, `--min-hold-up`), slack opcional (`--mass-balance-slack`), monotonicidad (`--enforce-monotonic-m`).
- Warm start robusto con sanitización de valores y hashing de configuración extendido.
- Métricas adicionales por iteración: `min_M_over_horizon`, violaciones top de constraints, drift ampliado.
- DSDA multi-start persistente con cache incremental y prueba `test_dsda_cache.py`.
- Overlay avanzado multi-run con paneles opcionales (hold-up, controles, tasas), modo columnas por run (`--per-run-columns`), estilos monotonic vs no-monotonic (`--monotonic-style-hint`), anotación de stats (`--annotate-stats`).
- Export de series completas de control (`control_series`) y nuevo CSV consolidado.
- Flag `--results-dir` en `run_enmpc` y `--output-dir` en overlay para organizar salidas.

### Changed
- Captura de snapshot primal evita valores negativos minúsculos en variables NonNegative.
- Hash de config incluye nuevos flags de estabilización y escalado (`rate_scale`).
- Checkpoints guardados opcionalmente con sufijos indexados cuando se usa `--results-dir`.

### Fixed
- Infeasibilidad causada por degeneración de M: bounds y monotonicidad previenen colapso numérico.
- Graficación: controles ya no aparecen como líneas horizontales ficticias (se exporta serie completa).
- Overlay: manejo correcto de ejes al usar modo columnas.

### Deprecated
- Uso de `--export-step-only` durante corridas que se planean reanudar (documentado como mala práctica).

### Tests
- `test_scaling_invariance.py`, `test_bounds_parameters.py`, `test_dsda_cache.py`.

---
## [0.2.x] - Fase 2 (Resumen)
- Kinetics detallada parcial, DSDA local, baseline de validación, hashing paramétrico.

## [0.1.x] - Fase 1
- Limpieza inicial, estructura base, scripts legacy integrados.

