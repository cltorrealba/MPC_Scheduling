# Ejemplo Básico ENMPC

Este ejemplo muestra un flujo mínimo para ejecutar una corrida ENMPC, reanudarla y generar overlays organizados.

## 1. Corrida inicial (24 h, horizonte 12 h, paso 6 h)
```powershell
python -m biorefinery.scripts.run_enmpc ^
  --total-time-h 24 --horizon-time-h 12 --step-time-h 6 ^
  --nfe 5 --warm-start ^
  --results-dir results/demo1 ^
  --output enmpc_seg1.json --max-iterations 2
```

## 2. Reanudar hasta completar
```powershell
python -m biorefinery.scripts.run_enmpc ^
  --total-time-h 24 --horizon-time-h 12 --step-time-h 6 ^
  --nfe 5 --warm-start ^
  --results-dir results/demo1 ^
  --resume-from enmpc_seg1.json --output enmpc_full.json
```

## 3. Versión comprimida (endpoints) posterior
```powershell
python -m biorefinery.scripts.run_enmpc ^
  --total-time-h 24 --horizon-time-h 12 --step-time-h 6 ^
  --nfe 5 --warm-start --export-step-only ^
  --results-dir results/demo1 ^
  --resume-from enmpc_full.json --output enmpc_full_compact.json
```

## 4. Overlay (especies y hold-up)
```powershell
python -m biorefinery.scripts.plot_enmpc_overlay ^
  --runs results/demo1/enmpc_full.json ^
  --species Eth,G,X --plot-holdup --normalize-hours ^
  --output-dir results/demo1/plots ^
  --output overlay_basic.png --export-csv overlay_basic.csv
```

## 5. Monotonicidad vs No-Monotonicidad
```powershell
python -m biorefinery.scripts.run_enmpc ^
  --total-time-h 36 --horizon-time-h 12 --step-time-h 6 --nfe 5 --warm-start ^
  --results-dir results/mono_comp ^
  --enforce-monotonic-m --output mono.json
python -m biorefinery.scripts.run_enmpc ^
  --total-time-h 36 --horizon-time-h 12 --step-time-h 6 --nfe 5 --warm-start ^
  --results-dir results/mono_comp ^
  --output nomono.json
python -m biorefinery.scripts.plot_enmpc_overlay ^
  --runs results/mono_comp/mono.json results/mono_comp/nomono.json ^
  --species Eth,G --plot-holdup --plot-controls --per-run-columns ^
  --monotonic-style-hint --annotate-stats --normalize-hours ^
  --output-dir results/mono_comp/plots --output overlay_compare.png
```

## Notas
- Evita usar `--export-step-only` antes de terminar si planeas reanudar.
- Usa `--seed` para reproducibilidad completa de perturbaciones.
- Con `--no-rates` puedes reducir el tamaño del JSON si no necesitas cinética.
