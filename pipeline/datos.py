"""
datos.py - Etapa 1 del pipeline: obtener los datos VERSIONADOS y separarlos por atleta.

    python -m pipeline.datos

Los datos no se guardan en este repositorio: se descargan del tag v1.0 de la Etapa 2 y se verifica
su SHA-256 contra params.yaml. Si alguien cambia el archivo de origen, la huella no coincide y el
pipeline se detiene (versionado de datos por contenido, sin depender de DVC).
"""
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from pipeline.comun import ETIQUETA, GRUPO, PARAMS, RAIZ, SEMILLA, VARIABLES, sha256

ARCHIVO = RAIZ / PARAMS["datos"]["archivo_local"]


class DatosNoCoinciden(Exception):
    pass


def descargar():
    """Descarga los bytes tal cual (sin pasar por pandas) para que el SHA-256 sea igual en cualquier SO."""
    from urllib.request import urlopen
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando datos versionados (~19 MB):\n  {PARAMS['datos']['url']}")
    with urlopen(PARAMS["datos"]["url"], timeout=120) as respuesta:
        ARCHIVO.write_bytes(respuesta.read())


def cargar(verificar=True):
    if not ARCHIVO.exists():
        descargar()
    huella = sha256(ARCHIVO)
    if verificar and huella != PARAMS["datos"]["sha256"]:
        raise DatosNoCoinciden(
            f"El SHA-256 de {ARCHIVO.name} ({huella[:12]}…) no coincide con params.yaml "
            f"({PARAMS['datos']['sha256'][:12]}…). Si los datos cambiaron a propósito, actualiza "
            "datos.url y datos.sha256 en params.yaml en un Pull Request.")
    return pd.read_csv(ARCHIVO)


def separar(datos):
    """80/20 por atleta (GroupShuffleSplit, semilla 42): idéntica a las Etapas 4, 5 y 6."""
    separador = GroupShuffleSplit(n_splits=1, test_size=PARAMS["datos"]["proporcion_prueba"], random_state=SEMILLA)
    idx_train, idx_test = next(separador.split(datos[VARIABLES], datos[ETIQUETA], groups=datos[GRUPO]))
    return datos.iloc[idx_train].reset_index(drop=True), datos.iloc[idx_test].reset_index(drop=True)


if __name__ == "__main__":
    df = cargar()
    entrenamiento, prueba = separar(df)
    print(f"{len(df):,} sesiones de {df[GRUPO].nunique()} atletas | SHA-256 verificado")
    print(f"Entrenamiento: {len(entrenamiento):,} sesiones ({entrenamiento[GRUPO].nunique()} atletas)")
    print(f"Prueba:        {len(prueba):,} sesiones ({prueba[GRUPO].nunique()} atletas)")
