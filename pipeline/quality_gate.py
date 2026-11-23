"""
quality_gate.py - Etapa 5 del pipeline: decide si el candidato se puede promover.

    python -m pipeline.quality_gate      # lee reportes/ y modelo/metadata.json (champion vigente)

Reglas en config/quality_gate.yaml: calidad mínima, no regresión contra el champion, estabilidad en
validación cruzada, equivalencia ONNX y fairness. Escribe reportes/quality_gate.json y un resumen en
Markdown (reportes/quality_gate.md) que GitHub Actions muestra en la página de la ejecución.
"""
import os
import sys

from pipeline.comun import CARPETA_MODELO, CARPETA_REPORTES, GATE, guardar_json, leer_json, titulo


def _regla(nombre, ok, valor, limite, bloqueante):
    estado = "ok" if ok else ("falla" if bloqueante else "advertencia")
    return {"regla": nombre, "estado": estado, "valor": valor, "limite": limite, "bloqueante": bloqueante}


def evaluar(metricas, onnx, champion=None, gate=GATE):
    reglas = []
    c = gate["calidad"]
    reglas.append(_regla("recall en prueba", metricas["prueba"]["recall"] >= c["recall_minimo"],
                         metricas["prueba"]["recall"], f">= {c['recall_minimo']}", c["bloqueante"]))
    reglas.append(_regla("ROC-AUC en prueba", metricas["prueba"]["roc_auc"] >= c["roc_auc_minimo"],
                         metricas["prueba"]["roc_auc"], f">= {c['roc_auc_minimo']}", c["bloqueante"]))

    n = gate["no_regresion"]
    if champion:
        ref = champion["metricas_prueba"]
        for k, tol in [("recall", n["caida_max_recall"]), ("roc_auc", n["caida_max_roc_auc"])]:
            caida = round(ref[k] - metricas["prueba"][k], 4)
            reglas.append(_regla(f"no regresión de {k} vs champion v{champion['version']}", caida <= tol,
                                 f"{metricas['prueba'][k]} (champion {ref[k]})", f"caída <= {tol}", n["bloqueante"]))
    else:
        reglas.append(_regla("no regresión vs champion", True, "sin champion previo", "-", False))

    e = gate["estabilidad"]
    desv = metricas["validacion_cruzada"]["resumen"]["recall"]["desviacion"]
    reglas.append(_regla("estabilidad: desviación del recall en CV", desv <= e["desviacion_max_recall"], desv,
                         f"<= {e['desviacion_max_recall']}", e["bloqueante"]))

    o = gate["onnx"]
    reglas.append(_regla("ONNX = scikit-learn (diferencia de probabilidad)",
                         onnx["diferencia_max"] <= o["max_diferencia_probabilidad"], f"{onnx['diferencia_max']:.2e}",
                         f"<= {o['max_diferencia_probabilidad']}", o["bloqueante"]))
    reglas.append(_regla("ONNX = scikit-learn (decisiones distintas)",
                         onnx["decisiones_distintas"] <= o["decisiones_distintas_max"], onnx["decisiones_distintas"],
                         f"<= {o['decisiones_distintas_max']}", o["bloqueante"]))

    f = gate["fairness"]
    grupos = [g for g in metricas["por_grupo"] if g["atributo"] in f["atributos"]]
    bajos = {f"{g['atributo']}={g['grupo']}": g["recall"] for g in grupos if g["recall"] < f["recall_minimo_por_grupo"]}
    reglas.append(_regla("fairness: recall mínimo por grupo", not bajos, bajos or "todos cumplen",
                         f">= {f['recall_minimo_por_grupo']}", f["bloqueante"]))
    for atributo in f["atributos"]:
        recalls = [g["recall"] for g in grupos if g["atributo"] == atributo]
        if len(recalls) > 1:
            brecha = round(max(recalls) - min(recalls), 4)
            reglas.append(_regla(f"fairness: brecha de recall por {atributo}", brecha <= f["brecha_recall_max"],
                                 brecha, f"<= {f['brecha_recall_max']}", f["bloqueante"]))

    aprobado = not any(r["estado"] == "falla" for r in reglas)
    return {"aprobado": aprobado, "version_candidato": metricas["version"],
            "version_champion": champion["version"] if champion else None, "reglas": reglas}


def a_markdown(resultado):
    iconos = {"ok": "✅", "advertencia": "⚠️", "falla": "❌"}
    lineas = [f"## Quality gate · candidato v{resultado['version_candidato']} "
              f"{'✅ APROBADO' if resultado['aprobado'] else '❌ RECHAZADO'}", "",
              f"Champion vigente: v{resultado['version_champion']}" if resultado["version_champion"] else "Sin champion previo",
              "", "| Regla | Estado | Valor | Límite | Bloqueante |", "|---|---|---|---|---|"]
    for r in resultado["reglas"]:
        lineas.append(f"| {r['regla']} | {iconos[r['estado']]} | {r['valor']} | {r['limite']} | {'sí' if r['bloqueante'] else 'no'} |")
    return "\n".join(lineas) + "\n"


def champion_vigente():
    """Ficha del modelo en producción. En un PR, CI la toma de main (variable CHAMPION_METADATA),
    porque modelo/ de la rama ya trae al candidato."""
    ruta = os.environ.get("CHAMPION_METADATA") or CARPETA_MODELO / "metadata.json"
    try:
        return leer_json(ruta)
    except (FileNotFoundError, ValueError, KeyError):
        return None


def aplicar(champion=None):
    titulo("Quality gate")
    resultado = evaluar(leer_json(CARPETA_REPORTES / "metricas.json"), leer_json(CARPETA_REPORTES / "calidad_onnx.json"),
                        champion)
    iconos = {"ok": "✅", "advertencia": "⚠️ ", "falla": "❌"}
    for r in resultado["reglas"]:
        print(f"  {iconos[r['estado']]} {r['regla']}: {r['valor']} ({r['limite']})")
    guardar_json(CARPETA_REPORTES / "quality_gate.json", resultado)
    md = a_markdown(resultado)
    (CARPETA_REPORTES / "quality_gate.md").write_text(md, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):                  # resumen visible en GitHub Actions
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    print(f"\n{'✅ Candidato APROBADO' if resultado['aprobado'] else '❌ Candidato RECHAZADO: no se promueve'}")
    return resultado


if __name__ == "__main__":
    sys.exit(0 if aplicar(champion_vigente())["aprobado"] else 1)
