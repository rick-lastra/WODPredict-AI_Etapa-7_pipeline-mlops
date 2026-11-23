# Guía de evidencias para el PDF del pipeline (Fase III, instrucción 5)

Guarda las capturas en `docs/capturas/` con estos nombres. Entre paréntesis, el criterio de la rúbrica que respalda.

| # | Archivo sugerido | Qué capturar | Criterio |
|---|---|---|---|
| 01 | `01_pipeline_local.png` | Terminal de VS Code con `python -m pipeline.ejecutar` completo (datos aprobados, gate aprobado, promoción, MLflow) | Pipeline |
| 02 | `02_pytest_ruff.png` | `pytest -v` (34 pruebas) y `ruff check .` | Pruebas |
| 03 | `03_mlflow_runs.png` | MLflow UI: experimento `etapa7-pipeline-mlops` con los runs | Versionado |
| 04 | `04_mlflow_registry.png` | MLflow UI > Models > `wodpredict-sobrecarga` con los alias `champion` / `challenger` | Versionado |
| 05 | `05_ci_verde.png` | GitHub > Actions > CI con los 3 jobs en verde | Integración continua |
| 06 | `06_quality_gate_resumen.png` | Resumen del job 2 con la tabla del quality gate | Auditoría |
| 07 | `07_ci_artefactos.png` | Artefacto `evidencias-pipeline-<sha>` descargable | Evidencias |
| 08 | `08_pr_v110.png` | Pull Request de v1.1.0 con los checks del CI | GitOps |
| 09 | `09_gate_v110.png` | Quality gate del PR v1.1.0: fairness en verde y no regresión contra v1.0.0 | Optimización basada en datos |
| 10 | `10_ci_rojo.png` | (Recomendado) un PR que rompe algo a propósito, por ejemplo `recall_minimo: 0.90`, y el CI en rojo bloqueando el merge | Pruebas |
| 11 | `11_cd_despliegue.png` | Actions > CD con publicar + desplegar en verde y el enlace al entorno `produccion` | Despliegue continuo |
| 12 | `12_ghcr_imagenes.png` | GitHub > Packages con las etiquetas `sha-…`, `v1.0.0`, `v1.1.0`, `latest` | Versionado de artefactos |
| 13 | `13_azure_revisiones.png` | Portal de Azure > Container App > *Revisions* (una por despliegue) | Despliegue |
| 14 | `14_api_produccion.png` | Formulario `/app` o `/docs` en la URL de Azure con `version_modelo` 1.1.0 | Funcional |
| 15 | `15_log_analytics.png` | Consulta KQL de `docs/despliegue_azure.md` con latencias | Monitoreo |
| 16 | `16_monitoreo.png` | Actions > Monitoreo con la prueba de humo programada | Monitoreo |
| 17 | `17_historial_git.png` | `git log --oneline --graph` o la vista de commits/tags en GitHub | Bitácora |

## Bitácora sugerida (tabla para el PDF)

| Fecha | Commit / PR | Qué cambió | Resultado del pipeline |
|---|---|---|---|
| | `main` inicial | Pipeline + modelo v1.0.0 reproducido | Gate aprobado con advertencia de fairness |
| | PR modelo/v1.1.0 | Sin `sex` + umbral por nivel | Gate aprobado, fairness en verde |
| | PR gate | `fairness.bloqueante: true` | Gate aprobado |
