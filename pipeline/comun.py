"""
comun.py - Rutas, parámetros y utilidades compartidas por todas las etapas del pipeline.

Todo lo que define al modelo sale de params.yaml (fuente única de verdad). Nada se escribe a mano
en el código: si cambia params.yaml, cambia el modelo, y eso queda registrado en Git.
"""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# En Windows la salida redirigida usa cp1252 y fallaría con los íconos ✅/❌: se fuerza UTF-8.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_CONFIG = RAIZ / "config"
CARPETA_MODELO = RAIZ / "modelo"                  # artefactos VERSIONADOS en Git (los que sirve la API)
CARPETA_CANDIDATO = RAIZ / "artefactos" / "candidato"   # salida de cada corrida (no se versiona)
CARPETA_REPORTES = RAIZ / "reportes"              # métricas y resultados de la corrida (no se versiona)


def leer_yaml(ruta):
    return yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))


PARAMS = leer_yaml(RAIZ / "params.yaml")
GATE = leer_yaml(CARPETA_CONFIG / "quality_gate.yaml")
REGLAS_DATOS = leer_yaml(CARPETA_CONFIG / "validacion_datos.yaml")

NUMERICAS = PARAMS["variables"]["numericas"]
CATEGORICAS = PARAMS["variables"]["categoricas"]
VARIABLES = NUMERICAS + CATEGORICAS
ETIQUETA = PARAMS["variables"]["etiqueta"]
GRUPO = PARAMS["variables"]["grupo"]
SEMILLA = PARAMS["modelo"]["semilla"]


def sha256(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def commit_git():
    """Commit actual (en GitHub Actions viene en GITHUB_SHA; en local se pregunta a git)."""
    import os
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "sin-commit"


def entorno():
    import numpy  # noqa: E401
    import pandas
    import sklearn
    return {"python": sys.version.split()[0], "sistema": platform.platform(),
            "numpy": numpy.__version__, "pandas": pandas.__version__, "scikit-learn": sklearn.__version__,
            "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def guardar_json(ruta, contenido):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    return ruta


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def titulo(texto):
    print(f"\n{'=' * 78}\n{texto}\n{'=' * 78}")
