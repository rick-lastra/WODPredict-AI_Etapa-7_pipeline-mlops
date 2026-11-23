"""
test_validacion_datos.py - Las pruebas de datos detectan datos defectuosos (sin descargar nada).

Se construye un dataset pequeño y válido a partir de los ejemplos de la API y se le inyecta un defecto
a la vez: el validador debe marcar la prueba correspondiente como "falla".
"""
import copy
import json

import numpy as np
import pandas as pd
import pytest

from pipeline.comun import REGLAS_DATOS
from pipeline.validacion_datos import crear_perfil, psi_por_variable, validar
from tests.conftest import RAIZ

REGLAS = copy.deepcopy(REGLAS_DATOS)
REGLAS["minimos"] = {"filas": 100, "atletas": 10}


@pytest.fixture
def datos():
    rng = np.random.default_rng(0)
    base = [json.loads((RAIZ / "tests" / "ejemplos" / f"atleta_riesgo_{n}.json").read_text(encoding="utf-8"))
            for n in ["bajo", "moderado", "alto"]]
    filas = []
    for i in range(300):
        fila = dict(base[i % 3])
        fila.update(athlete_id=f"A{i % 30:03d}", date=f"2025-01-{i // 30 + 1:02d}",
                    overreaching_label=int(i % 8 == 0), load_last_7d=float(rng.uniform(500, 2500)))
        filas.append(fila)
    return pd.DataFrame(filas)


def fallas(resultados):
    return [r["prueba"] for r in resultados if r["estado"] == "falla"]


def test_datos_validos_pasan(datos):
    assert fallas(validar(datos, REGLAS)) == []


def test_columna_faltante(datos):
    assert "esquema: columnas requeridas" in fallas(validar(datos.drop(columns=["acwr_load"]), REGLAS))


def test_valor_fuera_de_rango(datos):
    datos.loc[0, "prev_rpe"] = 15
    assert any("rangos" in f for f in fallas(validar(datos, REGLAS)))


def test_categoria_desconocida(datos):
    datos.loc[0, "level"] = "experto"
    assert "categorías válidas: level" in fallas(validar(datos, REGLAS))


def test_vacio_en_columna_obligatoria(datos):
    datos.loc[0, "load_last_7d"] = None
    assert any("obligatorias" in f for f in fallas(validar(datos, REGLAS)))


def test_duplicados(datos):
    assert any("duplicados" in f for f in fallas(validar(pd.concat([datos, datos.head(1)]), REGLAS)))


def test_etiqueta_no_binaria_y_prevalencia(datos):
    datos["overreaching_label"] = 1
    f = fallas(validar(datos, REGLAS))
    assert any("prevalencia" in x for x in f)


def test_drift_detectado(datos):
    perfil = crear_perfil(datos)
    corrido = datos.copy()
    corrido["load_last_7d"] = corrido["load_last_7d"] * 3          # la carga se triplica
    assert psi_por_variable(corrido, perfil)["load_last_7d"] > REGLAS["drift"]["psi_max"]
    assert any("drift" in f for f in fallas(validar(corrido, REGLAS, perfil)))
