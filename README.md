# 🏋️ WODPredict-AI: Pipeline MLOps/GitOps (Etapa 7 · Fase III)

> ## 🧭 Ruta del capstone · WODPredict-AI
>
> Este repositorio es la **etapa 7**, la que **integra** las seis anteriores en un solo pipeline automatizado: datos versionados → pruebas de datos → entrenamiento reproducible → quality gate → ONNX → Model Registry → imagen Docker → despliegue continuo en Azure Container Apps → monitoreo. Ver [Repositorios relacionados](#-repositorios-relacionados).

## 📌 Resumen
**Nombre del proyecto:** WODPredict-AI (Fase III. Resultados: solución de IA lista para la industria)

Hasta la Etapa 6 cada pieza del ciclo de vida existía, pero se ejecutaba a mano y en repositorios separados. Esta etapa las conecta con prácticas de **MLOps** (integración continua, pruebas automatizadas de código y de datos, versionado de datos, modelos y artefactos, despliegue continuo, monitoreo) y de **GitOps** (Git es la única fuente de verdad: el modelo, su configuración y la infraestructura se cambian **solo por Pull Request**, y lo que está en `main` es lo que corre en Azure).

**Objetivo General:**
Que cualquier cambio al modelo de riesgo de sobrecarga (datos, variables, umbral o código) llegue a producción **solo si** pasa pruebas automáticas, un quality gate de calidad, no regresión, equivalencia ONNX y fairness, y que cada predicción en producción se pueda rastrear hasta el commit, los datos y la versión del modelo que la produjeron.

**Contexto Profesional:**
Iniciativa alineada al *Business Case* de UnderCover Fitness (Fase I) para reducir en 25 % la deserción de atletas por lesiones asociadas a acumulación de fatiga. El modelo recomienda y el coach decide.

## 🔁 El pipeline en una imagen

```
 PR / push ──► CI (GitHub Actions) ───────────────────────────────────────────────────────────┐
              1 ruff ─► 2 datos (SHA-256) ─► validación de datos ─► pytest (34 pruebas)        │
                        ─► entrenamiento (CV por atleta + modelo final) ─► ONNX ─► QUALITY GATE │
                        ─► MLflow (run + registro) ─► ¿modelo/ se reproduce?  ─► 3 imagen + humo│
                                                                                              │
 merge a main ──► CD (solo si CI en main está verde) ──────────────────────────────────────────┤
              publica imagen en GHCR (sha-xxxxxxx, vX.Y.Z, latest)                             │
              aplica despliegue/containerapp.yaml en Azure Container Apps                      │
              prueba de humo en producción ─► si falla: ROLLBACK automático a la imagen anterior│
                                                                                              │
 cada hora ───► Monitoreo: salud, latencia y desviación Git ↔ producción ──────────────────────┘
```

| Práctica que pide la Fase III | Dónde está en este repo |
|---|---|
| Integración continua | `.github/workflows/ci.yml` (3 jobs, en cada push y PR) |
| Pruebas automatizadas de **código** | `tests/test_api.py`, `tests/test_quality_gate.py`, `ruff` |
| Pruebas automatizadas de **datos** | `pipeline/validacion_datos.py` + `config/validacion_datos.yaml` (esquema, vacíos, duplicados, categorías, rangos, prevalencia, fuga, drift PSI) y `tests/test_validacion_datos.py` |
| Versionado de **datos** | URL fija al tag `v1.0` + SHA-256 en `params.yaml` (si el archivo cambia, el pipeline se detiene) |
| Versionado de **modelos** | `params.yaml` (versión semántica), MLflow Model Registry con alias `champion` / `previous_champion` / `challenger` |
| Versionado de **artefactos** | `modelo/` en Git con SHA-256 en `metadata.json`; imágenes en GHCR etiquetadas por commit y por versión |
| Despliegue continuo | `.github/workflows/cd.yml` → Azure Container Apps, con prueba de humo y rollback |
| GitOps | `params.yaml` y `despliegue/containerapp.yaml` son el estado deseado; `verificar_reproducibilidad.py` impide fusionar un modelo que no sale del código |
| Monitoreo | `.github/workflows/monitoreo.yml` + logs JSON por consulta (Log Analytics) |
| Auditoría | Quality gate con reglas de fairness, ficha `modelo/metadata.json`, tags de commit en MLflow y en la imagen |

## 🧭 Guía rápida

| Pregunta | Respuesta |
|---|---|
| ¿Por dónde empiezo? | `python -m pipeline.ejecutar` corre todo el pipeline en local (≈ 20 s). |
| ¿Dónde se define el modelo? | `params.yaml`: variables, hiperparámetros, umbral, versión y datos (URL + SHA-256). |
| ¿Qué decide si un modelo se promueve? | `config/quality_gate.yaml`. |
| ¿Qué revisa en los datos? | `config/validacion_datos.yaml`. |
| ¿Cómo se despliega? | `despliegue/containerapp.yaml` (estado deseado) + `.github/workflows/cd.yml`. Ver `docs/despliegue_azure.md`. |
| ¿Por qué se tomó cada decisión? | `docs/decisiones_tecnicas.md`. |
| ¿Qué capturas necesito para el PDF? | `docs/guia_evidencias.md`. |

## ▶️ Ejecución local (VS Code + .venv, Windows)

```powershell
# 1. Ambiente
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Pipeline completo: descarga y verifica datos, valida, entrena, ONNX, quality gate, promueve y registra en MLflow
python -m pipeline.ejecutar

# 3. Pruebas automatizadas (código, datos, modelo y API)
pytest -v
ruff check .

# 4. Ver experimentos y Model Registry
mlflow ui --backend-store-uri sqlite:///mlflow.db       # http://127.0.0.1:5000

# 5. API en local (formulario en http://127.0.0.1:8000/app, Swagger en /docs)
uvicorn servicio.app:app --port 8000

# 6. Imagen Docker (Docker Desktop) y prueba de humo
docker build -t wodpredict-api:local .
docker run -d --name wodpredict -p 8000:8000 wodpredict-api:local
python scripts/smoke_test.py http://localhost:8000 --version-esperada 1.0.0
```

Cada etapa también se puede correr sola: `python -m pipeline.datos`, `python -m pipeline.validacion_datos`, `python -m pipeline.entrenar`, `python -m pipeline.quality_gate`, `python -m pipeline.verificar_reproducibilidad`.

## 🔀 Flujo de trabajo GitOps (cómo cambia el modelo)

1. Crear una rama: `git checkout -b modelo/v1.1.0`.
2. Cambiar **solo** `params.yaml` (por ejemplo, quitar `sex`, activar `umbral_por_nivel` y subir la versión a `1.1.0`).
3. Correr `python -m pipeline.ejecutar`. Si el quality gate aprueba, el pipeline actualiza `modelo/`.
4. `git add params.yaml modelo/ && git commit && git push` y abrir el Pull Request.
5. El CI vuelve a entrenar desde cero, aplica el quality gate contra el **champion de `main`** y verifica que `modelo/` del PR sale exactamente de `params.yaml` + datos. El resumen del gate aparece en la pestaña *Actions*.
6. Al fusionar, el CD publica la imagen `v1.1.0` y la despliega. Si la prueba de humo falla, vuelve sola a la imagen anterior.

**Prueba hecha en local:** con ese cambio el candidato v1.1.0 pasa todas las reglas, incluida fairness (recall de élite 0.62 → 0.81, brecha por nivel 0.18 → 0.07), con recall global 0.78 y el mismo ROC-AUC (0.859). Coincide con la mitigación B de la auditoría de la Etapa 6.

## 📊 Resultados del modelo vigente (v1.0.0, reproducido por el pipeline)

| Métrica (56 atletas nunca vistos, umbral 0.17) | Valor |
|---|---|
| Recall | 0.732 |
| Precisión | 0.378 |
| ROC-AUC | 0.859 |
| Validación cruzada por atleta (5 pliegues, recall) | 0.714 ± 0.025 |
| Diferencia ONNX vs scikit-learn | < 1e-6, 0 decisiones distintas |
| Diferencia contra el `model.pkl` de la Etapa 4 | ≈ 2e-10 (el pipeline reproduce el modelo original) |

El v1.0.0 **no cumple** la regla de fairness en atletas élite (recall 0.62). Por eso esa regla está como advertencia y se vuelve bloqueante al promover el v1.1.0.

## 🛠️ Tecnologías Utilizadas
*   **Lenguaje:** Python 3.12 · **Entorno:** VS Code, Docker Desktop
*   **Modelo:** scikit-learn 1.6.1 (regresión logística, `C = 0.1`), exportado a ONNX con `skl2onnx`
*   **Experimentos y registro:** MLflow 3.4 (tracking + Model Registry con alias)
*   **API:** FastAPI + Pydantic + uvicorn, inferencia con ONNX Runtime
*   **CI/CD:** GitHub Actions, GitHub Container Registry
*   **Nube:** Azure Container Apps (plan Consumption, México Central) con escalado KEDA (HTTP + cron) y Log Analytics
*   **Calidad:** pytest, ruff, actionlint

## 📂 Estructura

```
params.yaml                    Fuente única de verdad del modelo
config/                        quality_gate.yaml · validacion_datos.yaml · perfil_referencia.json (drift)
pipeline/                      datos · validacion_datos · entrenar · exportar_onnx · quality_gate · registrar · ejecutar · verificar_reproducibilidad
modelo/                        Artefactos versionados que sirve la API (model.onnx, model.pkl, metadata.json)
servicio/                      API FastAPI + formulario web
Dockerfile                     Imagen ligera (sin pandas ni scikit-learn)
despliegue/containerapp.yaml   Estado deseado en Azure Container Apps
scripts/                       smoke_test.py · azure_configurar.ps1 · desplegar.ps1 · azure_apagar.ps1
tests/                         34 pruebas: API, modelo, quality gate, datos
.github/workflows/             ci.yml · cd.yml · monitoreo.yml
docs/                          decisiones técnicas, despliegue en Azure, guía de evidencias
```

## 🧩 Repositorios relacionados

| Etapa | Repositorio | Qué reutiliza esta etapa |
|---|---|---|
| 1 | [WODPredict-AI_etapa-1_NLP-fatiga](https://github.com/rick-lastra/WODPredict-AI_etapa-1_NLP-fatiga) | Señal `prob_fatiga` (dos de las 23 variables) |
| 2 | [WODPredict-AI_etapa-2_preparacion-datos](https://github.com/rick-lastra/WODPredict-AI_etapa-2_preparacion-datos) | Dataset limpio `v1.0` (URL + SHA-256 en `params.yaml`) y el modelo elegido |
| 3 | [WODPredict-AI_etapa-3_evaluacion-modelo](https://github.com/rick-lastra/WODPredict-AI_etapa-3_evaluacion-modelo) | Umbral 0.17 y criterio recall ≥ 0.70 (regla de calidad del gate) |
| 4 | [WODPredict-AI_etapa-4_API-despliegue](https://github.com/rick-lastra/WODPredict-AI_etapa-4_API-despliegue) | Contrato de la API, pruebas, ejemplos y el despliegue en Azure |
| 5 | [WODPredict-AI_etapa-5_monitoreo-observabilidad](https://github.com/rick-lastra/WODPredict-AI_etapa-5_monitoreo-observabilidad) | Model Registry con alias, SLOs, logs JSON y criterio PSI de drift |
| 6 | [WODPredict-AI_etapa-6_escalabilidad-gobernanza](https://github.com/rick-lastra/WODPredict-AI_etapa-6_escalabilidad-gobernanza) | API ONNX, imagen ligera, política de escalado y auditoría de fairness |

## 👥 Contacto y Créditos
*   **Autor:** Ricardo Alejandro Lastra Dueñas
*   **Empresa (Caso de Uso):** UnderCover Fitness
*   **Fecha:** Noviembre 2026
*   **Institución:** Universidad Tecmilenio (Gestión de Proyectos de IA)
