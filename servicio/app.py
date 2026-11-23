"""
app.py - API de WODPredict-AI servida con ONNX Runtime (Etapa 7, Fase III).

Mismo contrato que las Etapas 4 y 6 (mismos endpoints, validaciones y respuesta). Cambios de la Etapa 7:
  - Lee TODO del modelo versionado (modelo/metadata.json): variables, umbral y, si existen,
    umbrales por nivel. Así el CD despliega cualquier versión que apruebe el pipeline sin tocar código.
  - Registra cada consulta como una línea JSON (request_id, latencia, estado, versión, riesgo) en
    stdout: en Azure Container Apps llega a Log Analytics (observabilidad de la Etapa 5).
    No registra los datos del atleta.

    uvicorn servicio.app:app --port 8000         (desde la raíz del repositorio)
"""
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. Cargar el modelo ONNX y su ficha UNA sola vez al iniciar
# ---------------------------------------------------------------------------
CARPETA = Path(__file__).resolve().parent
_por_defecto = CARPETA / "modelo" if (CARPETA / "modelo").exists() else CARPETA.parent / "modelo"
CARPETA_MODELO = Path(os.environ.get("CARPETA_MODELO", _por_defecto))
metadata = json.loads((CARPETA_MODELO / "metadata.json").read_text(encoding="utf-8"))
UMBRAL = metadata["umbral"]
UMBRALES_NIVEL = metadata.get("umbrales_por_nivel") or {}
NUMERICAS = metadata["variables_numericas"]
CATEGORICAS = metadata["variables_categoricas"]

opciones = ort.SessionOptions()
# Un hilo por consulta: el modelo es diminuto y en una réplica de 0.25 vCPU más hilos solo compiten
# por la misma CPU. La concurrencia se obtiene con más réplicas (escalado horizontal, Etapa 6).
opciones.intra_op_num_threads = 1
opciones.inter_op_num_threads = 1
sesion = ort.InferenceSession(str(CARPETA_MODELO / "model.onnx"), sess_options=opciones,
                              providers=["CPUExecutionProvider"])
SALIDA = ["probabilities"]

log = logging.getLogger("wodpredict")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# ---------------------------------------------------------------------------
# 2. Contrato de entrada (sin cambios desde la Etapa 4)
# ---------------------------------------------------------------------------
class DatosAtleta(BaseModel):
    level: Literal["novato", "intermedio", "élite"] = Field(description="Nivel del atleta")
    sex: Literal["F", "M"] = Field(description="Sexo")
    language: Literal["es", "en"] = Field(description="Idioma de sus comentarios")
    age: Optional[float] = Field(None, ge=16, le=80, description="Edad en años")
    days_since_first_session: int = Field(ge=0, le=3650, description="Días desde su primera sesión")
    days_since_prev_session: int = Field(ge=1, le=365, description="Días desde la sesión anterior")
    sessions_last_3d: int = Field(ge=0, le=3, description="Sesiones en los últimos 3 días")
    sessions_last_7d: int = Field(ge=0, le=7, description="Sesiones en los últimos 7 días")
    sessions_last_28d: int = Field(ge=0, le=28, description="Sesiones en los últimos 28 días")
    load_last_3d: float = Field(ge=0, le=10000, description="Carga de los últimos 3 días")
    load_last_7d: float = Field(ge=0, le=20000, description="Carga de los últimos 7 días")
    mean_session_load_28d: Optional[float] = Field(None, ge=0, le=5000, description="Carga promedio por sesión en 28 días")
    acwr3_freq: Optional[float] = Field(None, ge=0, le=4, description="ACWR de frecuencia (3 días)")
    acwr3_load: Optional[float] = Field(None, ge=0, le=4, description="ACWR de carga (3 días)")
    acwr_freq: Optional[float] = Field(None, ge=0, le=4, description="ACWR de frecuencia (7 días)")
    acwr_load: Optional[float] = Field(None, ge=0, le=4, description="ACWR de carga (7 días)")
    prev_rpe: Optional[float] = Field(None, ge=1, le=10, description="RPE de la sesión anterior (1 a 10)")
    prev_session_load: float = Field(ge=0, le=5000, description="Carga de la sesión anterior")
    prev_has_note: int = Field(ge=0, le=1, description="1 si dejó comentario en la sesión anterior")
    prob_fatiga_prev_session: Optional[float] = Field(None, ge=0, le=1, description="Prob. de fatiga del comentario anterior")
    prob_fatiga_last_note: Optional[float] = Field(None, ge=0, le=1, description="Prob. de fatiga del último comentario")
    days_since_last_note: Optional[float] = Field(None, ge=0, le=3650, description="Días desde el último comentario")
    notes_last_28d: int = Field(ge=0, le=60, description="Comentarios en los últimos 28 días")

    model_config = {"json_schema_extra": {"example": {
        "level": "élite", "sex": "F", "language": "es", "age": 31, "days_since_first_session": 365,
        "days_since_prev_session": 1, "sessions_last_3d": 2, "sessions_last_7d": 5, "sessions_last_28d": 18,
        "load_last_3d": 760, "load_last_7d": 1650, "mean_session_load_28d": 310,
        "acwr3_freq": 1.2, "acwr3_load": 1.3, "acwr_freq": 1.1, "acwr_load": 1.25,
        "prev_rpe": 8, "prev_session_load": 420, "prev_has_note": 1,
        "prob_fatiga_prev_session": 0.70, "prob_fatiga_last_note": 0.70,
        "days_since_last_note": 1, "notes_last_28d": 8}}}


class Prediccion(BaseModel):
    probabilidad: float
    umbral: float
    prediccion: int
    riesgo: str
    recomendacion: str
    version_modelo: str


def umbral_para(nivel):
    """Umbral global o, si el modelo lo trae, el umbral de su nivel (mitigación de fairness, Etapa 6)."""
    return UMBRALES_NIVEL.get(nivel, UMBRAL)


def clasificar_riesgo(probabilidad, umbral):
    if probabilidad >= 0.50:
        return "Alto", "Bajar la carga o programar descanso activo; revisar con el atleta."
    if probabilidad >= umbral:
        return "Moderado", "Revisar con el atleta antes de la sesión y considerar escalar el WOD."
    return "Bajo", "Entrenar según lo planeado."


def a_entradas(datos: dict):
    """JSON validado -> entradas del grafo ONNX (solo las variables del modelo). None -> NaN (se imputa)."""
    entradas = {c: np.array([[np.nan if datos[c] is None else datos[c]]], dtype=np.float32) for c in NUMERICAS}
    entradas.update({c: np.array([[datos[c]]], dtype=object) for c in CATEGORICAS})
    return entradas


# ---------------------------------------------------------------------------
# 3. Aplicación (mismos endpoints que la Etapa 4)
# ---------------------------------------------------------------------------
app = FastAPI(title="WODPredict-AI API (ONNX Runtime)",
              description="Modelo versionado y desplegado por el pipeline MLOps/GitOps de la Etapa 7.",
              version=metadata["version"])


@app.middleware("http")
async def registrar_consulta(request: Request, call_next):
    """Log estructurado por consulta (sin datos del atleta), igual al formato de la Etapa 5."""
    inicio = time.perf_counter()
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    respuesta = await call_next(request)
    respuesta.headers["x-request-id"] = request_id
    respuesta.headers["x-model-version"] = metadata["version"]
    log.info(json.dumps({"evento": "consulta", "request_id": request_id, "ruta": request.url.path,
                         "metodo": request.method, "estado_http": respuesta.status_code,
                         "latencia_ms": round((time.perf_counter() - inicio) * 1000, 2),
                         "version_modelo": metadata["version"]}))
    return respuesta


@app.get("/")
def health_check():
    return {"mensaje": "API funcionando", "modelo": metadata["nombre"], "version": metadata["version"],
            "motor": f"onnxruntime {ort.__version__}", "commit": os.environ.get("GIT_COMMIT", "local")}


@app.get("/modelo")
def info_modelo():
    return metadata


@app.post("/predict", response_model=Prediccion)
def predecir(datos: DatosAtleta):
    valores = datos.model_dump()
    probabilidad = float(sesion.run(SALIDA, a_entradas(valores))[0][0, 1])
    umbral = umbral_para(valores["level"])
    riesgo, recomendacion = clasificar_riesgo(probabilidad, umbral)
    return Prediccion(probabilidad=round(probabilidad, 4), umbral=umbral, prediccion=int(probabilidad >= umbral),
                      riesgo=riesgo, recomendacion=recomendacion, version_modelo=metadata["version"])


app.mount("/app", StaticFiles(directory=CARPETA / "frontend", html=True), name="frontend")


@app.get("/formulario", include_in_schema=False)
def ir_al_formulario():
    return RedirectResponse(url="/app/")
