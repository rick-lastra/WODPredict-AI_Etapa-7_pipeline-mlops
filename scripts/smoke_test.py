"""
smoke_test.py - Prueba de humo de la API desplegada (CI, CD y monitoreo programado).

    python scripts/smoke_test.py http://localhost:8000
    python scripts/smoke_test.py https://<app>.azurecontainerapps.io --version-esperada 1.0.0 --repeticiones 30

Solo usa la biblioteca estándar (corre en cualquier runner sin instalar nada). Comprueba:
  1. Health check (GET /) y que la versión desplegada sea la esperada (la de modelo/metadata.json en
     Git): si no coincide, producción se desvió de Git (GitOps).
  2. Los tres atletas de ejemplo devuelven el nivel de riesgo esperado y un dato inválido da 422.
  3. Latencia: p50 y p95 de N consultas a POST /predict (medida desde el cliente).
Escribe un resumen en Markdown en GitHub Actions y termina con código 1 si algo falla.
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = {n: json.loads((RAIZ / "tests" / "ejemplos" / f"atleta_riesgo_{n}.json").read_text(encoding="utf-8"))
            for n in ["bajo", "moderado", "alto"]}


def pedir(url, datos=None, timeout=30):
    cuerpo = None if datos is None else json.dumps(datos).encode()
    req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"})
    inicio = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), (time.perf_counter() - inicio) * 1000
    except urllib.error.HTTPError as e:
        return e.code, None, (time.perf_counter() - inicio) * 1000


def esperar(url, intentos):
    """Espera a que la API responda (arranque del contenedor o arranque en frío de Azure)."""
    for _ in range(intentos):
        try:
            if pedir(url + "/", timeout=10)[0] == 200:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--version-esperada", default=None)
    ap.add_argument("--repeticiones", type=int, default=20)
    ap.add_argument("--p95-max-ms", type=float, default=1000.0)
    ap.add_argument("--intentos-arranque", type=int, default=40)
    a = ap.parse_args()
    url = a.url.rstrip("/")
    resultados = []

    def revisar(nombre, ok, detalle):
        resultados.append((nombre, ok, detalle))
        print(f"  {'✅' if ok else '❌'} {nombre}: {detalle}")

    if not esperar(url, a.intentos_arranque):
        revisar("la API responde", False, f"{url} no respondió")
    else:
        _, salud, ms = pedir(url + "/")
        revisar("health check", True, f"v{salud['version']} · {salud['motor']} · commit {salud.get('commit', '?')[:8]} · {ms:.0f} ms")
        if a.version_esperada:
            revisar("versión desplegada = versión en Git", salud["version"] == a.version_esperada,
                    f"producción v{salud['version']} · Git v{a.version_esperada}")
        for nombre, datos in EJEMPLOS.items():
            estado, r, _ = pedir(url + "/predict", datos)
            ok = estado == 200 and r["riesgo"].lower() == nombre and r["prediccion"] == int(r["probabilidad"] >= r["umbral"])
            revisar(f"predicción atleta riesgo {nombre}", ok, f"HTTP {estado} · {r and r['riesgo']} · p={r and r['probabilidad']}")
        estado, _, _ = pedir(url + "/predict", EJEMPLOS["moderado"] | {"prev_rpe": 11})
        revisar("dato inválido rechazado", estado == 422, f"HTTP {estado}")
        tiempos = [pedir(url + "/predict", EJEMPLOS["moderado"])[2] for _ in range(a.repeticiones)]
        p95 = sorted(tiempos)[max(0, int(len(tiempos) * 0.95) - 1)]
        revisar(f"latencia p95 <= {a.p95_max_ms:.0f} ms ({a.repeticiones} consultas)", p95 <= a.p95_max_ms,
                f"p50 {statistics.median(tiempos):.0f} ms · p95 {p95:.0f} ms")

    aprobado = all(ok for _, ok, _ in resultados)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## Prueba de humo · {url} {'✅' if aprobado else '❌'}\n\n| Prueba | Estado | Detalle |\n|---|---|---|\n")
            f.writelines(f"| {n} | {'✅' if ok else '❌'} | {d} |\n" for n, ok, d in resultados)
    return 0 if aprobado else 1


if __name__ == "__main__":
    sys.exit(main())
