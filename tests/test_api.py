"""
test_api.py - Pruebas del contrato de la API (sin Docker, con el TestClient de FastAPI).

El contrato es el mismo desde la Etapa 4: si una versión nueva del modelo o del código lo rompe,
el CI falla y el cambio no llega a producción.
"""
import json

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from servicio import app as servicio
from tests.conftest import RAIZ

cliente = TestClient(servicio.app)
NOMBRES = ["bajo", "moderado", "alto"]
# Probabilidades documentadas por la Etapa 4 para el modelo v1.0.0 (simula_consumo.py)
ESPERADO_V1 = {"bajo": (0.030, "Bajo", 0), "moderado": (0.3025, "Moderado", 1), "alto": (0.7502, "Alto", 1)}


def ejemplo(nombre):
    return json.loads((RAIZ / "tests" / "ejemplos" / f"atleta_riesgo_{nombre}.json").read_text(encoding="utf-8"))


def test_health_check():
    r = cliente.get("/")
    assert r.status_code == 200
    assert r.json()["version"] == servicio.metadata["version"] and "onnxruntime" in r.json()["motor"]


def test_ficha_del_modelo():
    r = cliente.get("/modelo").json()
    assert r["version"] == servicio.metadata["version"] and r["quality_gate"] == "aprobado"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_onnx_igual_que_scikit_learn(nombre):
    """La API (ONNX) da la misma probabilidad que el Pipeline de scikit-learn versionado."""
    modelo = joblib.load(RAIZ / "modelo" / "model.pkl")
    datos = ejemplo(nombre)
    esperado = modelo.predict_proba(pd.DataFrame([datos]))[:, 1][0]
    r = cliente.post("/predict", json=datos).json()
    assert abs(r["probabilidad"] - esperado) <= 1e-3


@pytest.mark.skipif(servicio.metadata["version"] != "1.0.0", reason="valores de referencia solo para v1.0.0")
@pytest.mark.parametrize("nombre", NOMBRES)
def test_mismas_predicciones_que_etapa4(nombre):
    prob, riesgo, alerta = ESPERADO_V1[nombre]
    r = cliente.post("/predict", json=ejemplo(nombre)).json()
    assert abs(r["probabilidad"] - prob) <= 0.001
    assert r["riesgo"] == riesgo and r["prediccion"] == alerta and r["umbral"] == 0.17


def test_umbral_aplicado_es_el_del_nivel():
    datos = ejemplo("moderado")
    r = cliente.post("/predict", json=datos).json()
    assert r["umbral"] == servicio.umbral_para(datos["level"])
    assert r["prediccion"] == int(r["probabilidad"] >= r["umbral"])


def test_rechaza_dato_fuera_de_rango():
    r = cliente.post("/predict", json=ejemplo("moderado") | {"prev_rpe": 11})
    assert r.status_code == 422 and "prev_rpe" in r.text


def test_rechaza_categoria_invalida():
    r = cliente.post("/predict", json=ejemplo("moderado") | {"level": "experto"})
    assert r.status_code == 422


def test_vacios_se_imputan():
    datos = ejemplo("moderado") | {"age": None, "prev_rpe": None, "acwr_load": None}
    assert cliente.post("/predict", json=datos).status_code == 200


def test_mismo_contrato_de_respuesta():
    r = cliente.post("/predict", json=ejemplo("alto"))
    assert set(r.json()) == {"probabilidad", "umbral", "prediccion", "riesgo", "recomendacion", "version_modelo"}
    assert r.headers["x-model-version"] == servicio.metadata["version"] and r.headers["x-request-id"]
