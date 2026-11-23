"""
ejecutar.py - Orquestador del pipeline completo (local y GitHub Actions).

    python -m pipeline.ejecutar                  # corrida completa; si pasa el gate, actualiza modelo/
    python -m pipeline.ejecutar --sin-promover   # CI: entrena y evalúa, pero no toca modelo/
    python -m pipeline.ejecutar --sin-mlflow     # sin registro en MLflow (más rápido)

Etapas: 1) datos versionados  2) validación de datos  3) entrenamiento (CV + modelo final)
        4) ONNX + equivalencia  5) quality gate  6) promoción a modelo/  7) registro en MLflow

Código de salida 0 = candidato aprobado; 1 = datos rechazados o candidato rechazado.
"""
import argparse
import shutil
import sys
from datetime import date

from pipeline import entrenar as etapa_entrenar
from pipeline import exportar_onnx, quality_gate, validacion_datos
from pipeline.comun import (
    CARPETA_CANDIDATO,
    CARPETA_MODELO,
    CATEGORICAS,
    NUMERICAS,
    PARAMS,
    VARIABLES,
    commit_git,
    entorno,
    guardar_json,
    sha256,
    titulo,
)
from pipeline.datos import cargar, separar


def promover(metricas, onnx, gate):
    """Copia el candidato aprobado a modelo/ (lo que se versiona en Git y sirve la API) con su ficha."""
    titulo("Promoción a modelo/")
    CARPETA_MODELO.mkdir(exist_ok=True)
    for nombre in ["model.pkl", "model.onnx"]:
        shutil.copy2(CARPETA_CANDIDATO / nombre, CARPETA_MODELO / nombre)
    p = PARAMS["modelo"]
    fairness = {f"{g['atributo']}={g['grupo']}": g["recall"] for g in metricas["por_grupo"]}
    metadata = {
        "nombre": "WODPredict-AI - sobrecarga al día siguiente",
        "version": p["version"],
        "fecha_entrenamiento": date.today().isoformat(),
        "algoritmo": p["descripcion"],
        "umbral": p["umbral"],
        "umbrales_por_nivel": metricas["umbrales_por_nivel"],
        "dataset": PARAMS["datos"]["descripcion"],
        "dataset_sha256": PARAMS["datos"]["sha256"],
        "sesiones_entrenamiento": metricas["sesiones_entrenamiento"],
        "sesiones_prueba": metricas["sesiones_prueba"],
        "variables_numericas": NUMERICAS,
        "variables_categoricas": CATEGORICAS,
        "metricas_prueba": metricas["prueba"],
        "validacion_cruzada": metricas["validacion_cruzada"]["resumen"],
        "recall_por_grupo": fairness,
        "quality_gate": "aprobado" if gate["aprobado"] else "rechazado",
        "artefactos_sha256": onnx["sha256"],
        "git_commit_entrenamiento": commit_git(),
        "entorno": entorno(),
    }
    guardar_json(CARPETA_MODELO / "metadata.json", metadata)
    assert sha256(CARPETA_MODELO / "model.onnx") == onnx["sha256"]["model.onnx"]
    print(f"  modelo/ actualizado a v{p['version']}. Siguiente paso: git add modelo/ && git commit")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-promover", action="store_true", help="no copia el candidato a modelo/ (modo CI)")
    parser.add_argument("--sin-mlflow", action="store_true", help="no registra la corrida en MLflow")
    args = parser.parse_args(argv)

    titulo(f"Pipeline WODPredict-AI · candidato v{PARAMS['modelo']['version']} · commit {commit_git()[:8]}")
    champion = quality_gate.champion_vigente()                # se lee ANTES de que algo cambie modelo/

    if validacion_datos.main([]) != 0:
        return 1
    entrenamiento, prueba = separar(cargar())
    _, metricas = etapa_entrenar.entrenar(entrenamiento, prueba)
    u_vec = etapa_entrenar.umbrales_de(prueba["level"].to_numpy(), metricas["umbrales_por_nivel"])
    onnx = exportar_onnx.exportar(prueba, u_vec)
    gate = quality_gate.aplicar(champion)

    promovido = gate["aprobado"] and not args.sin_promover
    if promovido:
        promover(metricas, onnx, gate)
    if not args.sin_mlflow:
        from pipeline.registrar import registrar
        registrar(metricas, onnx, gate, prueba[VARIABLES].head(50), promovido)
    guardar_json(CARPETA_CANDIDATO / "resumen.json", {"gate": gate["aprobado"], "promovido": promovido,
                                                      "version": PARAMS["modelo"]["version"]})
    return 0 if gate["aprobado"] else 1


if __name__ == "__main__":
    sys.exit(main())
