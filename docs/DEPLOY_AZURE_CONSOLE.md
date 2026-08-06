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
export PYTHONIOENCODING=utf-8  # Windows: stops `az acr build` crashing mid-stream (see §1)

# The LIVE values — these are the deployed resources, not placeholders:
RG=afroeval-rg                 # resource group
LOC=eastus                     # region
ACR=afroevalacr0825            # Container Registry  ← NOT "afroevalacr"
ENV=afroeval-env               # Container Apps environment
APP=afroeval-console           # the Container App
TAG=v11                        # image tag — BUMP on every rebuild; see below
```

> **The registry is `afroevalacr0825`, not `afroevalacr`.** The name had to be globally
> unique, so a suffix was added at creation. An earlier version of this runbook carried the
> unsuffixed name, and every command failed at the first step with a misleading *"registry
> could not be found in subscription"*. Confirm with `az acr list -o table` if in doubt.

> **Check the last tag before picking the next.** As of 2026-08-06 the registry holds
> v2–v10 and the app runs **v10**, so the next build is `v11`:
> ```bash
> az acr repository show-tags -n "$ACR" --repository afroeval-console --orderby time_desc -o tsv | head -3
> ```

> **Never use `:latest`.** Container Apps caches by tag: if you rebuild `:latest` and
> `update --image …:latest`, it often keeps the *old* cached image and your change never
> ships. Always build + deploy a **fresh tag** (`v1`, `v2`, …) so Azure is forced to pull.

The Container Apps environment (below) is the slow one on a fresh subscription (5–20 min,
it auto-creates a Log Analytics workspace); if it errors on providers, run
`az provider register -n Microsoft.OperationalInsights --wait` and
`az provider register -n Microsoft.App --wait`, then retry.

```bash
az group create -n "$RG" -l "$LOC"
az acr create -n "$ACR" -g "$RG" --sku Basic --admin-enabled true
az containerapp env create -n "$ENV" -g "$RG" -l "$LOC"
```

## 1. Build the image (remote — no local Docker)

Run from the repo root (where the `Dockerfile` is):

```bash
az acr build --registry "$ACR" --image "afroeval-console:$TAG" .
```

> ⚠️ **On Windows this command often "fails" when the build is actually fine.** The build
> runs **remotely in Azure**; the CLI only streams its logs. Those logs contain characters
> `cp1252` cannot encode, so the local streamer dies with
> `UnicodeEncodeError: 'charmap' codec can't encode characters …` and a colorama
> traceback. **The remote build keeps going and usually succeeds.**
>
> The trap is that it reads as a build failure, and the natural reaction — re-running the
> build — queues a second job against the same tag. **Always check the run status before
> re-running:**
> ```bash
> az acr task list-runs -r "$ACR" --top 3 -o table       # Running / Succeeded / Failed
> az acr repository show-tags -n "$ACR" --repository afroeval-console --orderby time_desc -o tsv | head -3
> ```
> Prevent it with `export PYTHONIOENCODING=utf-8` before the build (see §0), or skip log
> streaming entirely with `--no-logs`. Hit on 2026-08-06 building v10.

First build is slow (torch + LaBSE ~1.8 GB baked in); later builds reuse cached layers.
The Dockerfile **pins** `deepeval==4.0.6` / `ragas==0.4.3` / `sentence-transformers==5.5.1`
— a loose `deepeval>=…` pulls a newer release that removed `LLMTestCaseParams`, breaking
the language-performance metrics. Keep them pinned.

## 2. Create the Container App

```bash
az containerapp create \
  -n "$APP" -g "$RG" --environment "$ENV" \
  --image "$ACR.azurecr.io/afroeval-console:$TAG" \
  --registry-server "$ACR.azurecr.io" \
  --target-port 8000 --ingress external --transport auto \
  --min-replicas 1 --max-replicas 1 \
  --cpu 2.0 --memory 4.0Gi
```

- `--transport auto` keeps WebSockets working (Streamlit requires them).
- `--min-replicas 1 --max-replicas 1`: always one warm instance → an in-progress eval
  subprocess is never torn down mid-run, and LaBSE stays resident (fast).
- `--cpu 2.0 --memory 4.0Gi`: LaBSE + torch resident ~2–2.5 GB; 4 GB is comfortable.
- The console launches each eval as a **subprocess** (`scripts/dispatch_run.py`), not a
  Streamlit worker thread — the eval stack arms `signal`-based timeouts that only work in
  a process's main thread. Nothing to configure; noted so you know why.

## 3. Set secrets + env

Store sensitive values as Container App **secrets**, then reference them as env vars.

```bash
az containerapp secret set -n "$APP" -g "$RG" --secrets \
  database-url="<SUPABASE_SESSION_POOLER_URL>" \
  supabase-url="<SUPABASE_URL>" \
  supabase-anon-key="<SUPABASE_ANON_KEY>" \
  operator-password="<OPERATOR_PASSWORD>" \
  azure-openai-api-key="<...>" \
  anthropic-api-key="<...>" \
  openai-api-key="<...>" \
  gemini-api-key="<...>"

az containerapp secret set -n "$APP" -g "$RG" --secrets \
  label-studio-url="<LABEL_STUDIO_URL>" \
  label-studio-api-key="<LABEL_STUDIO_API_KEY>"

az containerapp update -n "$APP" -g "$RG" \
  --set-env-vars \
    DATABASE_URL=secretref:database-url \
    SUPABASE_URL=secretref:supabase-url \
    SUPABASE_ANON_KEY=secretref:supabase-anon-key \
    OPERATOR_PASSWORD=secretref:operator-password \
    AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key \
    AZURE_OPENAI_ENDPOINT="<https://...openai.azure.com/>" \
    AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4.1-mini" \
    AZURE_OPENAI_API_VERSION="<e.g. 2024-06-01>" \
    OPENAI_API_VERSION="<same as AZURE_OPENAI_API_VERSION>" \
    AIL_JUDGE_PROVIDER="azure" \
    AIL_JUDGE_MODEL="gpt-4.1-mini" \
    ANTHROPIC_API_KEY=secretref:anthropic-api-key \
    OPENAI_API_KEY=secretref:openai-api-key \
    GEMINI_API_KEY=secretref:gemini-api-key \
    DEEPEVAL_ASYNC_MODE="true" \
    DEEPEVAL_MAX_CONCURRENCY="8" \
    JUDGE_MAX_CONCURRENCY="10" \
    LABEL_STUDIO_URL=secretref:label-studio-url \
    LABEL_STUDIO_API_KEY=secretref:label-studio-api-key \
    AFROEVAL_ENV="production" \
    HF_HOME=/models/hf
```

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Supabase session pooler (data) |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | console login (Supabase Auth — `auth/client.py`) |
| `OPERATOR_PASSWORD` | **unlocks Run Evaluation** (Category-2/admin) — required to launch runs |
| `AZURE_OPENAI_*` + `AIL_JUDGE_PROVIDER`/`AIL_JUDGE_MODEL` | LLM judge (Azure gpt-4.1-mini) |
| **`OPENAI_API_VERSION`** | the openai SDK's Azure client reads THIS name; set it = `AZURE_OPENAI_API_VERSION` or the judge errors "must provide api_version" |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | evaluated providers |
| **`DEEPEVAL_ASYNC_MODE=true`** | required — sync deepeval arms a signal-based timeout; also runs metrics concurrently (fast) |
| `DEEPEVAL_MAX_CONCURRENCY` / `JUDGE_MAX_CONCURRENCY` | run-speed tuning (8 / 10 for the 2M-TPM Azure judge) |
| **`LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY`** | required for HITL Management (authoring/validation/calibration) |
| `AFROEVAL_ENV` | `production` (quiets SQL echo, prod behavior) |
| `HF_HOME` | `/models/hf` — must match the Dockerfile so the baked LaBSE is found |

> These are all **required** for a fully-working console — each maps to a real failure we
> hit when it was missing. `AFROEVAL_SECRET_KEY` is only needed if you also run the FastAPI
> (`api.main`), not the Streamlit console, so skip it here.

Tip to avoid copy-paste errors: load `.env` into a map and reference it (watch for inline
`#` comments on some lines — strip them):
`Get-Content .env | %% { if ($_ -and -not $_.StartsWith('#') -and $_.Contains('=')) { $i=$_.IndexOf('='); $m[$_.Substring(0,$i).Trim()]=$_.Substring($i+1).Trim() } }`

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

**Bump the tag every time** (the `:latest` cache trap):

```bash
TAG=v11   # v12, v13, … — a NEW value each rebuild
az acr build --registry "$ACR" --image "afroeval-console:$TAG" .
az containerapp update -n "$APP" -g "$RG" \
  --image "$ACR.azurecr.io/afroeval-console:$TAG"
```

**Then verify the swap actually happened.** `provisioningState: Succeeded` means the
revision was *created*, not that it is serving. A 3 GB image loading LaBSE takes minutes
to activate, and Container Apps deliberately holds traffic on the old revision until the
new one is healthy — so an immediate `curl` returns 200 from the **old** build and looks
like success:

```bash
az containerapp revision list -n "$APP" -g "$RG" \
  --query "[?properties.active].{rev:name, image:properties.template.containers[0].image, \
health:properties.healthState, run:properties.runningState, traffic:properties.trafficWeight}" -o table
```

A finished cutover shows the new revision **Healthy / RunningAtMaxScale / traffic 100**
and the old one **Deprovisioning / traffic 0**. If the new revision goes **Unhealthy**,
traffic stays on the old build and nothing breaks for users — check container logs, and
suspect a missing env var or secret first.

## Troubleshooting

- **Change didn't take effect after a redeploy:** you reused an image tag. Container Apps
  caches by tag — build + deploy a **new** tag (`v2`, `v3`, …), never reuse `:latest`.
- **Eval finishes in seconds and a whole dimension is "Excluded":** its metrics errored
  `unavailable`. If the reason mentions deepeval (`'NoneType' … not callable` /
  `… has no attribute 'INPUT'`), the container's deepeval version drifted — confirm the
  Dockerfile pins `deepeval==4.0.6` and you deployed a fresh tag. Verify the metrics ran by
  checking a run's rows (0 errored = healthy).
- **`Run failed: … must provide … OPENAI_API_VERSION`:** set `OPENAI_API_VERSION` (the
  openai SDK's Azure client reads that exact name), equal to `AZURE_OPENAI_API_VERSION`.
- **`Run failed: signal only works in main thread`:** the console must dispatch via the
  `scripts/dispatch_run.py` subprocess (it does as of this branch); if you see this, the
  image predates that fix — rebuild from current `master`.
- **HITL Management actions error:** `LABEL_STUDIO_URL` / `LABEL_STUDIO_API_KEY` missing.
- **Blank page / "Please wait…" that never connects:** the WebSocket isn't getting
  through. Ensure `--transport auto` (or `http`) on ingress. If it persists behind the
  proxy, add XSRF/CORS relaxation as container-only Dockerfile `CMD` flags (do NOT edit the
  shared `.streamlit/config.toml`, which Streamlit Cloud also reads):
  `"--server.enableXsrfProtection=false", "--server.enableCORS=false"`.
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
