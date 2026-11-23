"""
test_datos_reales.py - Valida el dataset versionado completo (CI lo descarga antes de correr pytest).
"""
import pytest

from pipeline.comun import PARAMS, RAIZ, sha256

ARCHIVO = RAIZ / PARAMS["datos"]["archivo_local"]
pytestmark = [pytest.mark.datos,
              pytest.mark.skipif(not ARCHIVO.exists(), reason="sin datos locales: python -m pipeline.datos")]


def test_huella_de_los_datos():
    assert sha256(ARCHIVO) == PARAMS["datos"]["sha256"]


def test_contrato_de_datos_completo():
    from pipeline.comun import leer_json
    from pipeline.datos import cargar
    from pipeline.validacion_datos import RUTA_PERFIL, validar
    resultados = validar(cargar(), perfil=leer_json(RUTA_PERFIL))
    assert [r["prueba"] for r in resultados if r["estado"] == "falla"] == []
