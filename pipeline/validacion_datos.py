"""
validacion_datos.py - Etapa 2 del pipeline: pruebas automatizadas de DATOS.

    python -m pipeline.validacion_datos                    # valida los datos de params.yaml
    python -m pipeline.validacion_datos --actualizar-perfil  # regenera config/perfil_referencia.json

Revisa el contrato del dataset (config/validacion_datos.yaml) antes de entrenar:
esquema, vacíos, duplicados, categorías, rangos, prevalencia de la etiqueta, fuga de información y
data drift (PSI) contra el perfil de referencia del entrenamiento v1.0. Si una prueba bloqueante
falla, el pipeline se detiene y el modelo no se entrena.
"""
import argparse
import sys

import numpy as np
import pandas as pd

from pipeline.comun import (
    CARPETA_CONFIG,
    CARPETA_REPORTES,
    CATEGORICAS,
    ETIQUETA,
    GRUPO,
    NUMERICAS,
    REGLAS_DATOS,
    VARIABLES,
    guardar_json,
    leer_json,
    titulo,
)

RUTA_PERFIL = CARPETA_CONFIG / "perfil_referencia.json"


def _resultado(prueba, ok, detalle, bloqueante=True, advertencia=False):
    estado = "ok" if ok else ("advertencia" if advertencia or not bloqueante else "falla")
    return {"prueba": prueba, "estado": estado, "bloqueante": bloqueante, "detalle": detalle}


# ---------------------------------------------------------------------------
# Perfil de referencia y PSI (Population Stability Index), mismo criterio que la Etapa 5
# ---------------------------------------------------------------------------
def crear_perfil(entrenamiento, cortes=10):
    perfil = {"numericas": {}, "categoricas": {}}
    for c in NUMERICAS:
        valores = entrenamiento[c].dropna()
        bordes = np.unique(np.quantile(valores, np.linspace(0, 1, cortes + 1)))
        conteo = np.histogram(valores.clip(bordes[0], bordes[-1]), bins=bordes)[0]
        perfil["numericas"][c] = {"bordes": bordes.tolist(), "proporciones": (conteo / conteo.sum()).tolist()}
    for c in CATEGORICAS:
        perfil["categoricas"][c] = entrenamiento[c].value_counts(normalize=True).to_dict()
    return perfil


def psi(esperado, observado, eps=1e-4):
    e = np.clip(np.asarray(esperado, dtype=float), eps, None)
    o = np.clip(np.asarray(observado, dtype=float), eps, None)
    return float(np.sum((o - e) * np.log(o / e)))


def psi_por_variable(datos, perfil):
    salida = {}
    for c, ref in perfil["numericas"].items():
        bordes = np.array(ref["bordes"])
        valores = datos[c].dropna().clip(bordes[0], bordes[-1])
        conteo = np.histogram(valores, bins=bordes)[0]
        salida[c] = psi(ref["proporciones"], conteo / max(conteo.sum(), 1))
    for c, ref in perfil["categoricas"].items():
        obs = datos[c].value_counts(normalize=True)
        salida[c] = psi(list(ref.values()), [obs.get(k, 0.0) for k in ref])
    return salida


# ---------------------------------------------------------------------------
# Pruebas
# ---------------------------------------------------------------------------
def validar(datos: pd.DataFrame, reglas=REGLAS_DATOS, perfil=None):
    r = []
    faltan = [c for c in VARIABLES + [ETIQUETA, GRUPO, "date"] if c not in datos.columns]
    r.append(_resultado("esquema: columnas requeridas", not faltan, f"faltan: {faltan}" if faltan else "todas presentes"))
    if faltan:
        return r                                          # sin esquema no tiene sentido seguir

    r.append(_resultado("tamaño mínimo", len(datos) >= reglas["minimos"]["filas"]
                        and datos[GRUPO].nunique() >= reglas["minimos"]["atletas"],
                        f"{len(datos):,} filas, {datos[GRUPO].nunique()} atletas"))

    prohibidas = [c for c in reglas["columnas_prohibidas_como_variable"] if c in VARIABLES]
    r.append(_resultado("sin fuga: ninguna variable se conoce después de la sesión", not prohibidas,
                        f"variables prohibidas en params.yaml: {prohibidas}" if prohibidas else "ok"))

    etiqueta_binaria = set(datos[ETIQUETA].dropna().unique()) <= {0, 1}
    r.append(_resultado("etiqueta binaria (0/1)", etiqueta_binaria, f"valores: {[int(v) for v in sorted(datos[ETIQUETA].dropna().unique())[:5]]}"))
    prev = float(datos[ETIQUETA].mean())
    lo, hi = reglas["prevalencia_etiqueta"]
    r.append(_resultado("prevalencia de la etiqueta", lo <= prev <= hi, f"{prev:.3f} (esperado {lo} a {hi})"))

    dup = int(datos.duplicated([GRUPO, "date"]).sum())
    r.append(_resultado("sin duplicados (atleta + fecha)", dup <= reglas["max_duplicados"], f"{dup} duplicados"))

    nulos_obligatorios = {c: int(datos[c].isna().sum()) for c in reglas["sin_nulos"] if c in datos and datos[c].isna().any()}
    r.append(_resultado("sin vacíos en columnas obligatorias", not nulos_obligatorios, str(nulos_obligatorios or "ok")))
    prop = datos[VARIABLES].isna().mean()
    excesivos = prop[prop > reglas["max_nulos_columna"]].round(3).to_dict()
    r.append(_resultado(f"vacíos por variable <= {reglas['max_nulos_columna']:.0%}", not excesivos, str(excesivos or "ok")))

    for c, permitidas in reglas["categorias"].items():
        extra = sorted(set(datos[c].dropna().unique()) - set(permitidas))
        r.append(_resultado(f"categorías válidas: {c}", not extra, f"no permitidas: {extra}" if extra else "ok"))

    fuera = {}
    for c, (minimo, maximo) in reglas["rangos"].items():
        n = int(((datos[c] < minimo) | (datos[c] > maximo)).sum())
        if n:
            fuera[c] = n
    r.append(_resultado("rangos válidos (los mismos que valida la API)", not fuera, str(fuera or "ok")))

    if perfil is not None:
        cfg = reglas["drift"]
        valores = psi_por_variable(datos, perfil)
        peor = max(valores, key=valores.get)
        r.append(_resultado(f"data drift (PSI máx. <= {cfg['psi_max']})", valores[peor] <= cfg["psi_max"],
                            f"peor variable: {peor} (PSI {valores[peor]:.4f})", bloqueante=cfg["bloqueante"]))
        avisos = {k: round(v, 3) for k, v in valores.items() if cfg["psi_advertencia"] < v <= cfg["psi_max"]}
        if avisos:
            r.append(_resultado("data drift moderado (advertencia)", False, str(avisos), bloqueante=False))
    return r


def imprimir(resultados):
    iconos = {"ok": "✅", "advertencia": "⚠️ ", "falla": "❌"}
    for x in resultados:
        print(f"  {iconos[x['estado']]} {x['prueba']}: {x['detalle']}")


def main(argv=None):
    from pipeline.datos import cargar, separar
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--actualizar-perfil", action="store_true")
    args = parser.parse_args(argv)

    titulo("Validación de datos")
    datos = cargar()
    if args.actualizar_perfil or not RUTA_PERFIL.exists():
        entrenamiento, _ = separar(datos)
        guardar_json(RUTA_PERFIL, crear_perfil(entrenamiento))
        print(f"  Perfil de referencia guardado en {RUTA_PERFIL.name} (solo datos de entrenamiento)")
    resultados = validar(datos, perfil=leer_json(RUTA_PERFIL))
    imprimir(resultados)
    fallas = [x for x in resultados if x["estado"] == "falla"]
    guardar_json(CARPETA_REPORTES / "validacion_datos.json",
                 {"aprobado": not fallas, "pruebas": resultados, "filas": len(datos)})
    if fallas:
        print(f"\n❌ {len(fallas)} prueba(s) bloqueante(s) fallaron: el modelo NO se entrena.")
        return 1
    print("\n✅ Datos aprobados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
