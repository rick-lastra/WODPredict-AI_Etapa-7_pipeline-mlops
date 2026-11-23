# Decisiones técnicas del pipeline (Etapa 7)

Cada decisión sigue el formato: contexto, decisión, alternativas descartadas y evidencia.

## D1. Un repositorio integrador nuevo

- **Contexto:** las Etapas 1 a 6 viven en repositorios separados, cada uno responde una pregunta y se ejecuta a mano.
- **Decisión:** un repositorio nuevo que contiene todo el ciclo de vida, de los datos al despliegue, sin modificar las etapas anteriores (siguen como evidencia de cada fase).
- **Descartado:** agregar workflows al repo de la Etapa 6 (mezclaría el análisis de costos con la operación) o un monorepo con copias de todas las etapas (duplicaría código que ya no se usa).

## D2. Git como única fuente de verdad (GitOps)

- **Decisión:** el modelo se define en `params.yaml`, el despliegue en `despliegue/containerapp.yaml`, y los artefactos que se sirven viven en `modelo/`. Nada se cambia en el portal de Azure ni se sube un modelo a mano.
- **Cómo se garantiza:** `pipeline/verificar_reproducibilidad.py` vuelve a entrenar en CI y compara contra `modelo/` (tolerancia 1e-6). El monitoreo compara la versión en producción con la de `main`.
- **Evidencia:** el pipeline reproduce el `model.pkl` de la Etapa 4 con una diferencia máxima de 2e-10.

## D3. Versionado de datos por contenido (SHA-256) en lugar de DVC

- **Contexto:** el dataset limpio pesa 19 MB, es sintético e inmutable, y ya está publicado en el tag `v1.0` de la Etapa 2 y en Hugging Face.
- **Decisión:** URL fija al tag + SHA-256 en `params.yaml`. Si el contenido cambia, el pipeline se detiene.
- **Descartado:** DVC con almacenamiento remoto (Azure Blob). Agrega costo y configuración sin beneficio para un archivo que no cambia. Se adoptaría al llegar datos reales de Wodify (piloto de 6 meses).

## D4. Pruebas de datos con pandas y YAML en lugar de Great Expectations

- **Decisión:** un contrato de datos en `config/validacion_datos.yaml` aplicado por `pipeline/validacion_datos.py`: esquema, tamaño, fuga, etiqueta binaria, prevalencia (0.08 a 0.20), duplicados, vacíos, categorías, rangos (los mismos que valida la API) y drift con PSI contra un perfil del entrenamiento.
- **Por qué:** cero dependencias nuevas, se lee en un minuto y cada regla tiene una prueba unitaria que demuestra que detecta el defecto (`tests/test_validacion_datos.py`).
- **Descartado:** Great Expectations (≈ 100 dependencias para 13 reglas).

## D5. Reentrenar con todo el conjunto de entrenamiento después de la validación cruzada

- **Contexto:** recomendación de la docente en la Actividad 6.
- **Decisión:** `pipeline/entrenar.py` hace GroupKFold por atleta solo para medir estabilidad y calcular umbrales fuera de pliegue; el modelo que se evalúa, registra y despliega se entrena después con todo el entrenamiento (65,403 sesiones). El conjunto de prueba nunca se usa para decidir nada.

## D6. Quality gate con cinco familias de reglas

| Regla | Por qué | Bloqueante |
|---|---|---|
| Recall ≥ 0.70 y ROC-AUC ≥ 0.80 | SLO de calidad de la Etapa 5: un sobreentrenamiento no detectado es el error caro | Sí |
| No regresión vs champion (recall −0.02, AUC −0.01) | Un modelo nuevo no puede ser peor que el que ya está en producción | Sí |
| Desviación del recall en CV ≤ 0.05 | Evita promover un modelo que acertó por suerte en la partición de prueba | Sí |
| ONNX = scikit-learn (dif. ≤ 1e-4, 0 decisiones distintas) | La API sirve ONNX; tiene que decidir igual que el modelo evaluado | Sí |
| Fairness: recall ≥ 0.70 por grupo y brecha ≤ 0.10 | Igualdad de oportunidad (auditoría RAI de la Etapa 6) | Advertencia hoy; bloqueante desde v1.1.0 |

La regla de fairness no bloquea todavía porque el modelo en producción (v1.0.0) no la cumple en élite. Bloquearla hoy dejaría al sistema sin modelo; lo responsable es documentar la brecha, publicar el plan (v1.1.0) y endurecer la regla cuando exista un modelo que la cumpla.

## D7. MLflow local en desarrollo y como artefacto en CI

- **Decisión:** MLflow con backend SQLite (`mlflow.db`) en la máquina del desarrollador, donde vive el historial completo del Model Registry. En CI cada corrida crea su propio registro y lo guarda como artefacto descargable de GitHub Actions (30 días).
- **Descartado (por costo):** un servidor MLflow permanente en Azure (PostgreSQL + Blob, ≈ USD 15 a 30 al mes, más que toda la operación de la API). Se puede conectar sin tocar código con `MLFLOW_TRACKING_URI`.

## D8. GitHub Container Registry en lugar de Azure Container Registry

- **Decisión:** las imágenes se publican en GHCR, junto al código, etiquetadas por commit (inmutable), versión del modelo y `latest`.
- **Por qué:** gratis para el volumen del proyecto y sin credenciales extra para publicar (usa `GITHUB_TOKEN`). ACR Basic cuesta ≈ USD 5 al mes, que en la Etapa 6 era el único costo fijo.

## D9. CD que solo arranca con el CI de main en verde, con prueba de humo y rollback

- **Decisión:** `cd.yml` se dispara con `workflow_run` del CI en `main` y solo si terminó con éxito; despliega solo si el commit cambió algo desplegable. Antes de desplegar guarda la imagen vigente; si la prueba de humo en la URL pública falla, vuelve a esa imagen.
- **Relación con la Etapa 5:** automatiza el runbook de rollback (RB-02) que antes se ejecutaba a mano.

## D10. Escalado y tamaño de réplica

- **Decisión:** 0.25 vCPU / 0.5 GiB, de 0 a 5 réplicas y regla HTTP con 4 consultas concurrentes por réplica. Son los valores medidos en la Etapa 6, ahora aplicados de forma declarativa desde `despliegue/containerapp.yaml`.
- **Cambio frente a la Etapa 6 (evidencia del primer despliegue):** la regla cron (1 réplica de 04:45 a 21:15) no se aplica. El entorno de Container Apps se creó como *express* y Azure la rechazó (`ExpressCustomScaleRulesNotSupported`). El CD detectó el error, no cambió nada en producción y ejecutó el rollback.
- **Consecuencia:** la primera consulta después de un periodo sin tráfico paga un arranque en frío (≈ 10 s medido en la Etapa 6). Según el análisis de costos de la Etapa 6, con una consulta cada 12.5 s la réplica casi nunca llega a 0 en horario y se cobra a tarifa activa, así que esta configuración cuesta más que la configuración D (ver `resultados/costos_escenarios.csv` de la Etapa 6).
- **Alternativas para producción:** crear el entorno con perfiles de carga (`--enable-workload-profiles`), que sí admite la regla cron, o fijar `minReplicas: 1`. Ambas se cambian en un PR al mismo archivo.

## D11. Lo que no se automatiza (y por qué)

- **Reentrenamiento programado:** los datos son sintéticos y no cambian; un reentrenamiento nocturno siempre produciría el mismo modelo. El workflow de CI ya permite reentrenar con un clic (`workflow_dispatch`) y el plan es activarlo con datos reales y la alerta de drift.
- **Promoción automática a `main`:** el pipeline puede aprobar un candidato, pero la decisión de fusionar el PR es humana (el modelo recomienda y el coach decide; el pipeline propone y el responsable aprueba).
