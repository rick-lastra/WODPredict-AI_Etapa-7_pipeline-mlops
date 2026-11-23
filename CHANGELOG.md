# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). El modelo usa versionado semántico.

## [1.0.0] - 2026-11

### Agregado
- Pipeline automatizado de punta a punta (`pipeline/`): datos versionados por SHA-256, validación de datos, validación cruzada por atleta, entrenamiento final con todo el conjunto de entrenamiento, exportación a ONNX, quality gate, promoción y registro en MLflow.
- CI en GitHub Actions: ruff, 34 pruebas, pipeline completo, verificación de reproducibilidad, imagen Docker y prueba de humo.
- CD GitOps a Azure Container Apps con configuración declarativa, prueba de humo y rollback automático.
- Monitoreo programado de salud, latencia y desviación entre Git y producción.
- Modelo v1.0.0 reproducido desde el código (diferencia ≈ 2e-10 con el artefacto de la Etapa 4).
