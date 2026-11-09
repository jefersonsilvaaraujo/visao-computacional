# ---------------------------------------------------------------------------
# Etapa 1: baixa os pesos pré-treinados (YOLO e CLIP) e exporta para ONNX.
# Só roda no build (com internet). O PyTorch não vai para a imagem final.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS exportador
ARG MODELO_YOLO=yolo11n
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchvision==0.20.1 \
    && pip install torch==2.5.1 torchvision==0.20.1 ultralytics==8.3.40 onnx==1.17.0 open_clip_torch==2.29.0
WORKDIR /trabalho
COPY exportar_detector.py vocabulario.json ./
RUN mkdir -p /modelos && python exportar_detector.py ${MODELO_YOLO} /modelos vocabulario.json

# ---------------------------------------------------------------------------
# Etapa 2: imagem final, leve, que funciona sem internet.
# ---------------------------------------------------------------------------
FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 curl tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --from=exportador /modelos/ /app/modelos/
COPY servidor ./servidor
COPY static ./static
COPY tests ./tests
RUN useradd --create-home --uid 1000 demo && mkdir -p /app/dados /app/logs && chown -R demo /app/dados /app/logs
USER demo
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fs http://localhost:8000/api/status > /dev/null || exit 1
CMD ["uvicorn", "servidor.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "4000000", "--no-access-log"]
