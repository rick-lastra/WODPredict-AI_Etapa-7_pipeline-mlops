"""
verificar_reproducibilidad.py - Comprueba que modelo/ (lo versionado en Git) sale de params.yaml + datos.

    python -m pipeline.verificar_reproducibilidad     # después de: python -m pipeline.ejecutar --sin-promover

Principio GitOps: lo que está en Git es exactamente lo que se despliega. Si alguien cambia params.yaml
o el código de entrenamiento y no vuelve a correr el pipeline, o sube un modelo que no sale de este
código, esta prueba falla en el Pull Request y el cambio no se puede fusionar.
"""
import sys

import numpy as np

from pipeline.comun import CARPETA_CANDIDATO, CARPETA_MODELO, CARPETA_REPORTES, PARAMS, VARIABLES, leer_json, titulo
from pipeline.datos import cargar, separar
from pipeline.exportar_onnx import probabilidades_onnx

TOLERANCIA = 1e-6


def main():
    titulo("Verificación de reproducibilidad (modelo/ vs candidato recién entrenado)")
    errores = []
    metadata = leer_json(CARPETA_MODELO / "metadata.json")
    if metadata["version"] != PARAMS["modelo"]["version"]:
        errores.append(f"modelo/metadata.json es v{metadata['version']} pero params.yaml pide v{PARAMS['modelo']['version']}")
    if metadata["variables_numericas"] + metadata["variables_categoricas"] != VARIABLES:
        errores.append("las variables de modelo/metadata.json no coinciden con params.yaml")
    candidato = leer_json(CARPETA_REPORTES / "metricas.json")
    if metadata.get("umbrales_por_nivel") != candidato["umbrales_por_nivel"] or metadata["umbral"] != PARAMS["modelo"]["umbral"]:
        errores.append("los umbrales de modelo/metadata.json no coinciden con los del candidato")

    _, prueba = separar(cargar())
    if not errores:
        dif = np.abs(probabilidades_onnx(CARPETA_MODELO / "model.onnx", prueba[VARIABLES])
                     - probabilidades_onnx(CARPETA_CANDIDATO / "model.onnx", prueba[VARIABLES])).max()
        print(f"  Diferencia máx. de probabilidad en {len(prueba):,} sesiones: {dif:.2e} (tolerancia {TOLERANCIA})")
        if dif > TOLERANCIA:
            errores.append(f"modelo/model.onnx no se reproduce desde el código (diferencia {dif:.2e})")
    for e in errores:
        print(f"  ❌ {e}")
    if errores:
        print("\n  Corre `python -m pipeline.ejecutar` en local y haz commit de modelo/.")
        return 1
    print(f"  ✅ modelo/ v{metadata['version']} se reproduce exactamente desde params.yaml + datos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
