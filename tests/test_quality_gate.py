"""
test_quality_gate.py - El quality gate rechaza candidatos malos y deja pasar los buenos.
"""
import copy

from pipeline.quality_gate import evaluar

METRICAS = {"version": "9.9.9", "prueba": {"recall": 0.75, "roc_auc": 0.86},
            "validacion_cruzada": {"resumen": {"recall": {"media": 0.72, "desviacion": 0.02}}},
            "por_grupo": [{"atributo": "level", "grupo": g, "recall": r} for g, r in
                          [("novato", 0.78), ("intermedio", 0.74), ("élite", 0.72)]]}
ONNX = {"diferencia_max": 1e-7, "decisiones_distintas": 0}
CHAMPION = {"version": "1.0.0", "metricas_prueba": {"recall": 0.7324, "roc_auc": 0.8593}}


def reglas_fallidas(resultado):
    return [r["regla"] for r in resultado["reglas"] if r["estado"] == "falla"]


def test_candidato_bueno_se_aprueba():
    assert evaluar(METRICAS, ONNX, CHAMPION)["aprobado"]


def test_recall_bajo_se_rechaza():
    m = copy.deepcopy(METRICAS)
    m["prueba"]["recall"] = 0.60
    r = evaluar(m, ONNX, CHAMPION)
    assert not r["aprobado"] and "recall en prueba" in reglas_fallidas(r)


def test_regresion_contra_champion_se_rechaza():
    m = copy.deepcopy(METRICAS)
    m["prueba"]["roc_auc"] = 0.84                      # cae 0.019 > 0.01
    assert not evaluar(m, ONNX, CHAMPION)["aprobado"]


def test_onnx_que_decide_distinto_se_rechaza():
    assert not evaluar(METRICAS, {"diferencia_max": 1e-7, "decisiones_distintas": 3}, CHAMPION)["aprobado"]


def test_inestable_en_validacion_cruzada_se_rechaza():
    m = copy.deepcopy(METRICAS)
    m["validacion_cruzada"]["resumen"]["recall"]["desviacion"] = 0.09
    assert not evaluar(m, ONNX, CHAMPION)["aprobado"]


def test_fairness_bloquea_solo_si_es_bloqueante():
    m = copy.deepcopy(METRICAS)
    m["por_grupo"][2]["recall"] = 0.60
    gate = copy.deepcopy(__import__("pipeline.comun", fromlist=["GATE"]).GATE)
    gate["fairness"]["bloqueante"] = False
    assert evaluar(m, ONNX, CHAMPION, gate)["aprobado"]
    gate["fairness"]["bloqueante"] = True
    assert not evaluar(m, ONNX, CHAMPION, gate)["aprobado"]
