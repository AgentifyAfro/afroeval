# Console-on-Azure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the existing Streamlit console (with `.[eval]` + LaBSE) as a container and deploy it to Azure Container Apps, so a full evaluation — including LaBSE and the divergence signal — can be launched from the browser and run in-process on Azure.

**Architecture:** No app code change. The console keeps dispatching the eval in-process; it just runs in a container with the memory + LaBSE to complete it. Supabase Auth + Postgres unchanged. Config comes from container env vars.

**Tech Stack:** Streamlit (existing console), Docker, Azure Container Apps + ACR, CPU-torch + sentence-transformers/LaBSE, Supabase.

## Global Constraints

- **Spec is the contract:** `docs/superpowers/specs/2026-08-02-azure-eval-backend-design.md`.
- **No change to scoring / evaluators / dispatch / divergence / auth logic.** This is packaging + deployment. The only code that may change is a config *read* if one proves Streamlit-Cloud-specific (none expected).
- **CPU-only torch** in the image (`--extra-index-url https://download.pytorch.org/whl/cpu`); **bake `sentence-transformers/LaBSE`** at build with a fixed `HF_HOME` (zero runtime download).
- **Container image runs Streamlit headless** on `0.0.0.0:8000`; health endpoint `GET /_stcore/health`; ingress must allow **WebSockets** (Streamlit requires them).
- The console reads config from **env vars** via pydantic settings — container env vars are sufficient (the existing `st.secrets.get(...)` sync is try/except-wrapped and degrades to env). Required env: `DATABASE_URL`, `AFROEVAL_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_DEPLOYMENT_NAME`/`AZURE_OPENAI_API_VERSION`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `HF_HOME`.
- Venv `./.venv/Scripts/python.exe`; full pytest suite stays green; `ruff` clean; commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

- `Dockerfile` *(new)* — the console image (Task 1).
- `.dockerignore` *(new)* — build-context excludes (Task 1).
- `.streamlit/config.toml` *(new)* — headless/ingress-compatible server config (Task 1).
- `docs/DEPLOY_AZURE_CONSOLE.md` *(new)* — copy-paste `az` runbook + secrets table + smoke test (Task 2).

---

### Task 1: Console container image (Dockerfile + .dockerignore + Streamlit config)

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `.streamlit/config.toml`

**Interfaces:** produces a container that serves the Streamlit console with `.[eval]` + LaBSE resident. No unit test (built remotely via `az acr build`); correctness by review + the offline checks in Step 4.

- [ ] **Step 1: Write `.streamlit/config.toml`**

```toml
[server]
headless = true
address = "0.0.0.0"
port = 8000
enableCORS = false
enableXsrfProtection = false
# ^ relaxed because the app sits behind Azure Container Apps ingress (single origin,
#   HTTPS-terminated). Revisit if a custom domain / stricter origin policy is added.

[browser]
gatherUsageStats = false
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/hf \
    TRANSFORMERS_OFFLINE=0

WORKDIR /app

# Deps first (cached layer): CPU-only torch, then the project with the eval extra.
COPY pyproject.toml README* ./
RUN pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install ".[eval]"

# App code
COPY . .
RUN pip install --no-deps -e .

# Bake LaBSE into the image (zero runtime download; deterministic deploys)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/LaBSE')"

EXPOSE 8000
CMD ["streamlit", "run", "console/app.py", \
     "--server.port=8000", "--server.address=0.0.0.0", "--server.headless=true"]
```

> If the project's build backend needs the full source for metadata at `pip install ".[eval]"` time, collapse the two `COPY` steps into a single `COPY . .` before install — verify against `pyproject.toml`'s `[build-system]` during implementation and adjust. Keep the LaBSE-bake step last so it stays cached across app-code changes.

- [ ] **Step 3: Write `.dockerignore`**

```
.venv/
venv/
.git/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
tests/
docs/
.superpowers/
.env
*.log
```

Keep `benchmarks/`, `console/`, `auth/`, `api/`, `orchestration/`, `evaluators/`, `scoring/`, `db/`, `reporting/`, and `.streamlit/` in the image.

- [ ] **Step 4: Offline validation (no Docker needed).** Confirm:
  - `./.venv/Scripts/python.exe -c "import console.app"` succeeds (the containerized entrypoint imports).
  - `pip install ".[eval]"` target matches `pyproject.toml` `[project.optional-dependencies].eval`.
  - The LaBSE model id matches `evaluators/language_performance.py` (`sentence-transformers/LaBSE`).
  - Full suite green: `./.venv/Scripts/python.exe -m pytest tests/ -q -p no:warnings`; `ruff check .` clean (Dockerfile/config are not Python, so ruff is unaffected — just ensure no stray code changes).

- [ ] **Step 5: Commit** — `git commit -m "build: containerize the Streamlit console for Azure (CPU-torch, LaBSE baked in)"`

---

### Task 2: Azure deploy runbook + config docs

**Files:**
- Create: `docs/DEPLOY_AZURE_CONSOLE.md`

**Interfaces:** documentation only; reviewed for completeness/correctness of the `az` commands, the env/secrets table, WebSocket ingress, health probe, and smoke test.

- [ ] **Step 1: Write `docs/DEPLOY_AZURE_CONSOLE.md`** covering, concretely:

  - **Prereqs:** `az login`; an ACR name; a resource group; a Container Apps environment.
  - **Build the image remotely (no local Docker):**
    `az acr build --registry <ACR> --image afroeval-console:latest .`
  - **Create the Container App:**
    - `--min-replicas 1 --max-replicas 1` (always warm; in-process eval thread never torn down; LaBSE resident)
    - `--cpu 2.0 --memory 4.0Gi`
    - external ingress, target port `8000`, **transport enabling WebSockets** (`--transport auto`/`http` per Container Apps WebSocket support)
    - liveness probe → `GET /_stcore/health`
    - env/secrets below
  - **Env / secrets** (Container App secrets, referenced by env):
    | Var | Purpose |
    |---|---|
    | `DATABASE_URL` | Supabase session pooler |
    | `AFROEVAL_SECRET_KEY` | app secret key |
    | `SUPABASE_URL`, `SUPABASE_ANON_KEY` | console login (Supabase Auth) |
    | `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT_NAME` / `AZURE_OPENAI_API_VERSION` | LLM judge |
    | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | evaluated providers |
    | `HF_HOME` | `/models/hf` (matches the Dockerfile) |
  - **First-run checks:** `curl -s $URL/_stcore/health` (200); open the URL, log in (Supabase Auth), confirm views render.
  - **Smoke run:** launch a small eval from the browser → it completes; `multilingual_similarity` scores (not `unavailable`); the per-run divergence callout + "Div" markers appear; scorecard renders.
  - **Update/redeploy:** `az acr build ...` then `az containerapp update --image <ACR>.azurecr.io/afroeval-console:latest`.
  - **Cutover & fallback:** keep the Streamlit Cloud deployment live during cutover as a fallback; retire it once Azure is proven. `scripts/run_eval.py` in `.venv` remains a fallback throughout. Note the known limitation: a container restart (deploy/crash) drops an in-progress in-process run — same behavior as today; re-run if it happens.

- [ ] **Step 2: Commit** — `git commit -m "docs: Azure console deploy runbook + config"`

---

## Self-Review

**Spec coverage:** Dockerfile w/ CPU-torch + LaBSE baked (Task 1) ✓ · Streamlit headless/ingress config (Task 1) ✓ · Container Apps always-warm + 4 GB + WebSocket ingress + `/_stcore/health` probe (Task 2) ✓ · full env/secrets incl. Supabase Auth (Task 2, names confirmed from `auth/client.py`) ✓ · no app code change / config resolves from env (constraints + Task 1 Step 4) ✓ · migrations unchanged (constraints) ✓ · Cloud kept as fallback during cutover (Task 2) ✓.

**Placeholder scan:** the `<ACR>` / `<URL>` tokens in Task 2 are user-supplied deploy values (documented as such), not unfilled plan blanks. The Task 1 Step-2 build-backend caveat is an explicit verify-and-adjust instruction.

**Type consistency:** env-var names are consistent across the Dockerfile (`HF_HOME`), the constraints list, and the Task 2 secrets table; `SUPABASE_URL`/`SUPABASE_ANON_KEY` match `api/settings.py` (`supabase_url`/`supabase_anon_key`) and `auth/client.py`.

**Note:** both tasks are packaging/docs, not TDD-able; the real gate is `az acr build` + the post-deploy browser smoke run, plus the offline import/suite checks in Task 1 Step 4.
