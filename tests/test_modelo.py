"""
test_modelo.py - Pruebas del ARTEFACTO versionado en modelo/ (lo que despliega el CD).
"""
import json

from pipeline.comun import CARPETA_MODELO, PARAMS, VARIABLES, sha256

META = json.loads((CARPETA_MODELO / "metadata.json").read_text(encoding="utf-8"))


def test_version_y_variables_coinciden_con_params():
    assert META["version"] == PARAMS["modelo"]["version"]
    assert META["variables_numericas"] + META["variables_categoricas"] == VARIABLES
    assert META["umbral"] == PARAMS["modelo"]["umbral"]


def test_huellas_de_los_artefactos():
    """El SHA-256 registrado en la ficha corresponde a los archivos (nadie los cambió a mano)."""
    for nombre, huella in META["artefactos_sha256"].items():
        assert sha256(CARPETA_MODELO / nombre) == huella, nombre


def test_datos_de_entrenamiento_trazables():
    assert META["dataset_sha256"] == PARAMS["datos"]["sha256"]


def test_paso_el_quality_gate_y_cumple_slo_de_calidad():
    assert META["quality_gate"] == "aprobado"
    assert META["metricas_prueba"]["recall"] >= 0.70


def test_onnx_pesa_poco():
    assert (CARPETA_MODELO / "model.onnx").stat().st_size < 50_000
