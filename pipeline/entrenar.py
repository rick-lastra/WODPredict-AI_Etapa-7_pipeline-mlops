"""
entrenar.py - Etapa 3 del pipeline: validación cruzada, entrenamiento final y evaluación.

    python -m pipeline.entrenar

1. Validación cruzada agrupada por atleta (GroupKFold) SOLO con el conjunto de entrenamiento:
   mide la estabilidad del modelo y produce predicciones fuera de pliegue (para el umbral por nivel).
2. Con la validación cruzada terminada, el modelo final se vuelve a entrenar con TODO el conjunto de
   entrenamiento (recomendación de la docente en la Actividad 6) antes de evaluarlo y registrarlo.
3. Evaluación en el conjunto de prueba (atletas nunca vistos): métricas globales y por grupo
   (nivel, sexo, idioma) para la auditoría de fairness del quality gate.

Salida: artefactos/candidato/model.pkl y reportes/metricas.json. Todavía NO toca modelo/.
"""
import sys

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pipeline.comun import (
    CARPETA_CANDIDATO,
    CARPETA_REPORTES,
    CATEGORICAS,
    ETIQUETA,
    GRUPO,
    NUMERICAS,
    PARAMS,
    SEMILLA,
    VARIABLES,
    guardar_json,
    titulo,
)

P = PARAMS["modelo"]


def crear_modelo():
    """Imputar con la mediana + escalar, One-Hot de categorías y regresión logística (igual que la Etapa 4)."""
    numericas = Pipeline([("imputar", SimpleImputer(strategy="median")), ("escalar", StandardScaler())])
    prep = ColumnTransformer([("num", numericas, NUMERICAS),
                              ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS)])
    return Pipeline([("prep", prep),
                     ("modelo", LogisticRegression(C=P["C"], max_iter=P["max_iter"], random_state=SEMILLA))])


def umbrales_de(niveles, umbrales_por_nivel):
    """Vector de umbrales: uno por sesión según su nivel (o el umbral global)."""
    if not umbrales_por_nivel:
        return np.full(len(niveles), P["umbral"])
    return np.array([umbrales_por_nivel.get(n, P["umbral"]) for n in niveles])


def metricas(y, prob, umbral):
    pred = (prob >= umbral).astype(int)
    return {"exactitud": round(accuracy_score(y, pred), 4),
            "precision": round(precision_score(y, pred, zero_division=0), 4),
            "recall": round(recall_score(y, pred, zero_division=0), 4),
            "f1": round(f1_score(y, pred, zero_division=0), 4),
            "roc_auc": round(float(roc_auc_score(y, prob)), 4) if len(set(y)) > 1 else None,
            "tasa_alertas": round(float(pred.mean()), 4)}


def validacion_cruzada(entrenamiento):
    """GroupKFold por atleta: métricas por pliegue y probabilidades fuera de pliegue."""
    X, y, g = entrenamiento[VARIABLES], entrenamiento[ETIQUETA].to_numpy(), entrenamiento[GRUPO]
    oof = np.zeros(len(y))
    pliegues = []
    for i, (a, b) in enumerate(GroupKFold(n_splits=PARAMS["validacion_cruzada"]["folds"]).split(X, y, g), 1):
        m = crear_modelo().fit(X.iloc[a], y[a])
        oof[b] = m.predict_proba(X.iloc[b])[:, 1]
        pliegues.append({"pliegue": i, **metricas(y[b], oof[b], P["umbral"])})
    resumen = {k: {"media": round(float(np.mean([p[k] for p in pliegues])), 4),
                   "desviacion": round(float(np.std([p[k] for p in pliegues])), 4)}
               for k in ["recall", "precision", "roc_auc"]}
    return pliegues, resumen, oof


def calcular_umbrales_por_nivel(entrenamiento, oof):
    """Por nivel, el umbral más alto <= umbral global que alcanza el recall objetivo (fuera de pliegue)."""
    y = entrenamiento[ETIQUETA].to_numpy()
    salida = {}
    for nivel in sorted(entrenamiento["level"].unique()):
        mask = (entrenamiento["level"] == nivel).to_numpy()
        elegido = P["umbral"]
        for u in np.round(np.arange(P["umbral"], 0.0, -0.01), 2):
            elegido = float(u)
            if recall_score(y[mask], (oof[mask] >= u).astype(int)) >= P["recall_objetivo_por_nivel"]:
                break
        salida[nivel] = elegido
    return salida


def por_grupo(prueba, prob, umbral_vec, atributos=("level", "sex", "language")):
    filas = []
    for atributo in atributos:
        for grupo, idx in prueba.groupby(atributo).groups.items():
            i = prueba.index.get_indexer(idx)
            filas.append({"atributo": atributo, "grupo": grupo, "atletas": int(prueba.loc[idx, GRUPO].nunique()),
                          "sesiones": int(len(i)), **metricas(prueba[ETIQUETA].to_numpy()[i], prob[i], umbral_vec[i])})
    return filas


def entrenar(entrenamiento, prueba):
    titulo(f"Entrenamiento del candidato v{P['version']}")
    print(f"  Variables: {len(NUMERICAS)} numéricas + {len(CATEGORICAS)} categóricas {CATEGORICAS}")
    pliegues, cv, oof = validacion_cruzada(entrenamiento)
    print(f"  Validación cruzada ({len(pliegues)} pliegues por atleta): recall {cv['recall']['media']} "
          f"± {cv['recall']['desviacion']} | ROC-AUC {cv['roc_auc']['media']} ± {cv['roc_auc']['desviacion']}")

    umbrales_nivel = calcular_umbrales_por_nivel(entrenamiento, oof) if P["umbral_por_nivel"] else None
    if umbrales_nivel:
        print(f"  Umbrales por nivel (fuera de pliegue): {umbrales_nivel}")

    # Modelo final: TODO el conjunto de entrenamiento (después de la validación cruzada).
    modelo = crear_modelo().fit(entrenamiento[VARIABLES], entrenamiento[ETIQUETA])
    prob = modelo.predict_proba(prueba[VARIABLES])[:, 1]
    u_vec = umbrales_de(prueba["level"].to_numpy(), umbrales_nivel)
    globales = metricas(prueba[ETIQUETA].to_numpy(), prob, u_vec)
    print(f"  Prueba ({prueba[GRUPO].nunique()} atletas nunca vistos): {globales}")

    CARPETA_CANDIDATO.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, CARPETA_CANDIDATO / "model.pkl")
    reporte = {"version": P["version"], "umbral": P["umbral"], "umbrales_por_nivel": umbrales_nivel,
               "sesiones_entrenamiento": int(len(entrenamiento)), "sesiones_prueba": int(len(prueba)),
               "atletas_entrenamiento": int(entrenamiento[GRUPO].nunique()),
               "atletas_prueba": int(prueba[GRUPO].nunique()),
               "validacion_cruzada": {"resumen": cv, "pliegues": pliegues},
               "prueba": globales, "por_grupo": por_grupo(prueba, prob, u_vec)}
    guardar_json(CARPETA_REPORTES / "metricas.json", reporte)
    return modelo, reporte


if __name__ == "__main__":
    from pipeline.datos import cargar, separar
    entrenar(*separar(cargar()))
    sys.exit(0)
