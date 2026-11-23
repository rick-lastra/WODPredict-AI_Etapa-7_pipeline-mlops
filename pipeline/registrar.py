"""
registrar.py - Etapa 6 del pipeline: seguimiento en MLflow y Model Registry con alias.

Cada corrida queda como un run de MLflow (parámetros, métricas, reportes, commit de Git, SHA-256 de
los datos y de los artefactos). El candidato se registra como nueva versión de "wodpredict-sobrecarga"
con el alias `challenger`; si pasa el quality gate y se promueve, recibe `champion` y la versión
anterior queda como `previous_champion` (destino del rollback, patrón de la Etapa 5).

Por defecto MLflow es local (mlflow.db + mlruns/). Para un servidor remoto basta con definir la
variable de entorno MLFLOW_TRACKING_URI.
"""
import contextlib
import io
import os

import joblib
import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature

from pipeline.comun import CARPETA_CANDIDATO, CARPETA_REPORTES, NUMERICAS, PARAMS, RAIZ, VARIABLES, commit_git, titulo

NOMBRE = PARAMS["modelo"]["nombre"]
EXPERIMENTO = "etapa7-pipeline-mlops"


def configurar():
    uri = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}")
    mlflow.set_tracking_uri(uri)
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        cliente = MlflowClient()
        if cliente.get_experiment_by_name(EXPERIMENTO) is None:
            destino = None if uri.startswith("http") else (RAIZ / "mlruns").as_uri()
            cliente.create_experiment(EXPERIMENTO, artifact_location=destino)
    mlflow.set_experiment(EXPERIMENTO)
    return uri


def _aplanar(prefijo, d):
    return {f"{prefijo}_{k}": float(v) for k, v in d.items() if isinstance(v, (int, float)) and v is not None}


def registrar(metricas, onnx, gate, ejemplo, promovido):
    titulo("Registro en MLflow")
    uri = configurar()
    p = PARAMS["modelo"]
    modelo = joblib.load(CARPETA_CANDIDATO / "model.pkl")
    ejemplo = ejemplo.astype({c: "float64" for c in NUMERICAS})   # firma con números decimales (admiten vacíos)
    with mlflow.start_run(run_name=f"candidato_v{p['version']}") as run:
        mlflow.log_params({"version": p["version"], "C": p["C"], "umbral": p["umbral"],
                           "umbral_por_nivel": p["umbral_por_nivel"], "variables": len(VARIABLES),
                           "categoricas": ",".join(PARAMS["variables"]["categoricas"]),
                           "dataset": PARAMS["datos"]["descripcion"], "dataset_sha256": PARAMS["datos"]["sha256"][:16]})
        mlflow.log_metrics(_aplanar("prueba", metricas["prueba"]))
        cv = metricas["validacion_cruzada"]["resumen"]
        mlflow.log_metrics({f"cv_{k}_{e}": v for k, d in cv.items() for e, v in d.items()})
        mlflow.log_metrics({"onnx_diferencia_max": onnx["diferencia_max"], "gate_aprobado": float(gate["aprobado"])})
        mlflow.set_tags({"etapa": "7", "git_commit": commit_git(), "quality_gate": "aprobado" if gate["aprobado"] else "rechazado",
                         "sha256_onnx": onnx["sha256"]["model.onnx"]})
        for nombre in ["metricas.json", "calidad_onnx.json", "quality_gate.json", "quality_gate.md", "validacion_datos.json"]:
            if (CARPETA_REPORTES / nombre).exists():
                mlflow.log_artifact(str(CARPETA_REPORTES / nombre), artifact_path="reportes")
        mlflow.log_artifact(str(CARPETA_CANDIDATO / "model.onnx"), artifact_path="onnx")
        firma = infer_signature(ejemplo, modelo.predict_proba(ejemplo)[:, 1])
        with contextlib.redirect_stderr(io.StringIO()):
            info = mlflow.sklearn.log_model(modelo, name="modelo", signature=firma, input_example=ejemplo.head(3),
                                            registered_model_name=NOMBRE)
    cliente = MlflowClient()
    version = str(info.registered_model_version)
    for k, v in {"version_semantica": p["version"], "git_commit": commit_git()[:12],
                 "quality_gate": "aprobado" if gate["aprobado"] else "rechazado"}.items():
        cliente.set_model_version_tag(NOMBRE, version, k, v)
    cliente.set_registered_model_alias(NOMBRE, "challenger", version)
    if promovido:
        try:
            anterior = cliente.get_model_version_by_alias(NOMBRE, "champion").version
            cliente.set_registered_model_alias(NOMBRE, "previous_champion", anterior)
        except Exception:
            anterior = None
        cliente.set_registered_model_alias(NOMBRE, "champion", version)
        cliente.delete_registered_model_alias(NOMBRE, "challenger")
        print(f"  {NOMBRE} v{version} -> champion" + (f" (previous_champion = v{anterior})" if anterior else ""))
    else:
        print(f"  {NOMBRE} v{version} -> challenger (no promovido)")
    print(f"  Run {run.info.run_id[:8]} en {uri}  |  ver con: mlflow ui --backend-store-uri {uri}")
    return version
