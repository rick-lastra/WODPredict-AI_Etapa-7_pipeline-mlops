# Dockerfile - Imagen de la API de WODPredict-AI (Etapa 7). Base: imagen ligera de la Etapa 6.
# Se construye desde la RAÍZ del repositorio (la usa el CD de GitHub Actions):
#   docker build -t wodpredict-api:local .
#   docker run -d --name wodpredict -p 8000:8000 wodpredict-api:local
# Buenas prácticas: imagen slim, usuario sin privilegios, HEALTHCHECK, puerto por variable PORT y
# el commit de Git como etiqueta y variable de entorno (trazabilidad imagen -> código -> modelo).
FROM python:3.12-slim

ARG GIT_COMMIT=local
ARG MODEL_VERSION=desconocida
LABEL org.opencontainers.image.source="https://github.com/rick-lastra/WODPredict-AI_Etapa-7_pipeline-mlops" \
      org.opencontainers.image.revision=$GIT_COMMIT \
      org.opencontainers.image.version=$MODEL_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GIT_COMMIT=$GIT_COMMIT

WORKDIR /app

COPY servicio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servicio/app.py .
COPY servicio/frontend/ frontend/
COPY modelo/model.onnx modelo/metadata.json modelo/

RUN useradd --create-home appuser
USER appuser

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/')" || exit 1

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
