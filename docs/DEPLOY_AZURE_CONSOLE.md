# Deploy the AfroEval console to Azure Container Apps

Runs the Streamlit operator console — with the full eval stack (`.[eval]`) and LaBSE —
on Azure, so a complete evaluation (including `multilingual_similarity` and the
judge-divergence signal) executes in-process where there is memory + the model. This
replaces the Streamlit Cloud limitation (LaBSE can't load in its ~1 GB ceiling).

Design: `docs/superpowers/specs/2026-08-02-azure-eval-backend-design.md`.
Image: root `Dockerfile` (CPU-torch + LaBSE baked in). **No local Docker needed** —
`az acr build` builds remotely.

---

## 0. Prerequisites

```bash
az login
# Pick / set these once:
RG=afroeval-rg                 # resource group
LOC=eastus                     # region
ACR=afroevalacr                # Container Registry name (must be globally unique)
ENV=afroeval-env               # Container Apps environment
APP=afroeval-console           # the Container App
```

```bash
az group create -n "$RG" -l "$LOC"
az acr create -n "$ACR" -g "$RG" --sku Basic
az containerapp env create -n "$ENV" -g "$RG" -l "$LOC"
```

## 1. Build the image (remote — no local Docker)

Run from the repo root (where the `Dockerfile` is):

```bash
az acr build --registry "$ACR" --image afroeval-console:latest .
```

First build is slow (torch + LaBSE ~1.8 GB baked in); later builds reuse cached layers.

## 2. Create the Container App

```bash
az containerapp create \
  -n "$APP" -g "$RG" --environment "$ENV" \
  --image "$ACR.azurecr.io/afroeval-console:latest" \
  --registry-server "$ACR.azurecr.io" \
  --target-port 8000 --ingress external --transport auto \
  --min-replicas 1 --max-replicas 1 \
  --cpu 2.0 --memory 4.0Gi
```

- `--transport auto` keeps WebSockets working (Streamlit requires them).
- `--min-replicas 1 --max-replicas 1`: always one warm instance → the in-process eval
  thread is never torn down mid-run, and LaBSE stays resident (fast).
- `--cpu 2.0 --memory 4.0Gi`: LaBSE + torch resident ~2–2.5 GB; 4 GB is comfortable.

## 3. Set secrets + env

Store sensitive values as Container App **secrets**, then reference them as env vars.

```bash
az containerapp secret set -n "$APP" -g "$RG" --secrets \
  database-url="<SUPABASE_SESSION_POOLER_URL>" \
  afroeval-secret-key="<STRONG_RANDOM_KEY>" \
  supabase-url="<SUPABASE_URL>" \
  supabase-anon-key="<SUPABASE_ANON_KEY>" \
  azure-openai-api-key="<...>" \
  anthropic-api-key="<...>" \
  openai-api-key="<...>" \
  gemini-api-key="<...>"

az containerapp update -n "$APP" -g "$RG" \
  --set-env-vars \
    DATABASE_URL=secretref:database-url \
    AFROEVAL_SECRET_KEY=secretref:afroeval-secret-key \
    SUPABASE_URL=secretref:supabase-url \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
    AZURE_OPENAI_ENDPOINT="<https://...openai.azure.com/>" \
    AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4.1-mini" \
    AZURE_OPENAI_API_VERSION="<e.g. 2024-06-01>" \
    ANTHROPIC_API_KEY=secretref:anthropic-api-key \
    OPENAI_API_KEY=secretref:openai-api-key \
    GEMINI_API_KEY=secretref:gemini-api-key \
    HF_HOME=/models/hf
```

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Supabase session pooler (data) |
| `AFROEVAL_SECRET_KEY` | app secret key |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | console login (Supabase Auth — `auth/client.py`) |
| `AZURE_OPENAI_*` | LLM judge (gpt-4.1-mini) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | evaluated providers |
| `HF_HOME` | `/models/hf` — must match the Dockerfile so the baked LaBSE is found |

Non-secret note: the DB must be at head (the deploy-migrate workflow already handles
prod migrations; the console container does not migrate).

## 4. First-run checks

```bash
URL=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
curl -s "https://$URL/_stcore/health"     # -> "ok"
```

Then open `https://$URL`, log in (Supabase Auth), and confirm views render.

**Smoke run:** launch a small single-pack eval from the browser →
- it completes (status → completed);
- `multilingual_similarity` **scores** (not `unavailable`);
- the per-run **judge-divergence callout** + **"Div"** markers appear;
- the scorecard renders and the PDF downloads.

## 5. Redeploy after code changes

```bash
az acr build --registry "$ACR" --image afroeval-console:latest .
az containerapp update -n "$APP" -g "$RG" \
  --image "$ACR.azurecr.io/afroeval-console:latest"
```

## Troubleshooting

- **Blank page / "Please wait…" that never connects:** the WebSocket isn't getting
  through. Ensure `--transport auto` (or `http`) on ingress. If it persists behind the
  proxy, add XSRF/CORS relaxation as container-only CMD flags (do NOT edit the shared
  `.streamlit/config.toml`, which Streamlit Cloud also reads): redeploy with the
  Dockerfile `CMD` appended `"--server.enableXsrfProtection=false", "--server.enableCORS=false"`.
- **`multilingual_similarity` still `unavailable`:** the image didn't bake LaBSE or
  `HF_HOME` mismatched — confirm the Dockerfile bake step ran and `HF_HOME=/models/hf`
  in both the image and the env.
- **Login fails:** `SUPABASE_URL` / `SUPABASE_ANON_KEY` missing or wrong.
- **OOM / restarts under load:** raise `--memory` (e.g. 6–8 Gi).

## Rollback / fallback

- Keep the **Streamlit Cloud** deployment live during cutover; retire it only once Azure
  is proven. `scripts/run_eval.py` in `.venv` remains a local fallback throughout.
- Known limitation (same as today): a container restart (deploy/crash) drops an
  **in-progress** in-process run — just re-launch it. If this becomes a problem, the
  documented upgrade is the API-worker / job-queue split (see the spec's non-goals).
