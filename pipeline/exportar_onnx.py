"""
exportar_onnx.py - Etapa 4 del pipeline: convierte el candidato a ONNX y verifica que decide igual.

    python -m pipeline.exportar_onnx

La API sirve el modelo con ONNX Runtime (Etapa 6: CPU por consulta ≈ 9 veces menor e imagen sin
pandas ni scikit-learn). Esta etapa garantiza que el grafo ONNX da las mismas probabilidades y las
mismas decisiones que el Pipeline de scikit-learn en todo el conjunto de prueba.
"""
import joblib
import numpy as np
import onnx
import onnxruntime as ort
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType, StringTensorType

from pipeline.comun import (
    CARPETA_CANDIDATO,
    CARPETA_REPORTES,
    CATEGORICAS,
    NUMERICAS,
    PARAMS,
    VARIABLES,
    guardar_json,
    sha256,
    titulo,
)

RUTA_PKL = CARPETA_CANDIDATO / "model.pkl"
RUTA_ONNX = CARPETA_CANDIDATO / "model.onnx"


def entradas_onnx(df):
    entradas = {c: df[[c]].to_numpy(dtype=np.float32) for c in NUMERICAS}
    entradas.update({c: df[[c]].astype(str).to_numpy(dtype=object) for c in CATEGORICAS})
    return entradas


def probabilidades_onnx(ruta, df):
    sesion = ort.InferenceSession(str(ruta), providers=["CPUExecutionProvider"])
    return sesion.run(["probabilities"], entradas_onnx(df))[0][:, 1]


def convertir(modelo, ruta=RUTA_ONNX):
    tipos = [(c, FloatTensorType([None, 1])) for c in NUMERICAS] + [(c, StringTensorType([None, 1])) for c in CATEGORICAS]
    onx = convert_sklearn(modelo, initial_types=tipos, target_opset={"": 17, "ai.onnx.ml": 3},
                          options={id(modelo): {"zipmap": False}})
    onx.doc_string = f"WODPredict-AI v{PARAMS['modelo']['version']} (pipeline Etapa 7)"
    onnx.checker.check_model(onx)
    ruta.write_bytes(onx.SerializeToString())
    return ruta


def exportar(prueba, umbral_vec):
    titulo("Exportación a ONNX y prueba de equivalencia")
    modelo = joblib.load(RUTA_PKL)
    convertir(modelo)
    X = prueba[VARIABLES]
    p_sk = modelo.predict_proba(X)[:, 1]
    p_onnx = probabilidades_onnx(RUTA_ONNX, X)
    dif = np.abs(p_sk - p_onnx)
    distintas = int(((p_sk >= umbral_vec) != (p_onnx >= umbral_vec)).sum())
    resultado = {"sesiones_comparadas": int(len(X)), "diferencia_max": float(dif.max()),
                 "diferencia_media": float(dif.mean()), "decisiones_distintas": distintas,
                 "bytes": {"model.pkl": RUTA_PKL.stat().st_size, "model.onnx": RUTA_ONNX.stat().st_size},
                 "sha256": {"model.pkl": sha256(RUTA_PKL), "model.onnx": sha256(RUTA_ONNX)},
                 "versiones": {"onnx": onnx.__version__, "onnxruntime": ort.__version__,
                               "skl2onnx": __import__("skl2onnx").__version__}}
    print(f"  {len(X):,} sesiones | diferencia máx. {dif.max():.2e} | decisiones distintas: {distintas}")
    guardar_json(CARPETA_REPORTES / "calidad_onnx.json", resultado)
    return resultado
