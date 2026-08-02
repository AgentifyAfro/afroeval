# AfroEval console — Azure Container Apps image.
# Runs the Streamlit operator console with the full eval stack (.[eval]) + LaBSE,
# so a full evaluation (incl. multilingual_similarity + judge-divergence) runs
# in-process here, where there is memory + the model — unlike Streamlit Cloud.
#
# Build remotely (no local Docker needed):
#   az acr build --registry <ACR> --image afroeval-console:latest .
# See docs/DEPLOY_AZURE_CONSOLE.md.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf \
    TRANSFORMERS_OFFLINE=0

WORKDIR /app

# 1) Heavy, stable ML deps FIRST so they stay cached across app-code changes.
#    CPU-only torch (LaBSE runs on CPU — avoids the multi-GB CUDA wheels), then the
#    eval extras. PINNED to the versions verified working locally: a newer deepeval
#    removed `LLMTestCaseParams` (used by the language-performance metrics), so a loose
#    `deepeval>=1.4.0` silently pulled an incompatible release and those metrics errored.
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install "sentence-transformers==5.5.1" "deepeval==4.0.6" "ragas==0.4.3"

# 2) Bake LaBSE into the image → zero runtime download, deterministic deploys.
#    Cached: depends only on the layer above, not on app code.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/LaBSE')"

# 3) App source + install the project. hatchling needs the full source to build the
#    wheel, so the source is copied before install; the heavy deps above are already
#    satisfied, so this layer is fast and only adds the base project dependencies.
COPY . .
RUN pip install ".[eval]"

EXPOSE 8000

# Streamlit headless behind Azure Container Apps ingress. Health: GET /_stcore/health
CMD ["streamlit", "run", "console/app.py", \
     "--server.port=8000", "--server.address=0.0.0.0", "--server.headless=true"]
