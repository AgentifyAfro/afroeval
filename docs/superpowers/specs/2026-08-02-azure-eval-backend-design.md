# Design — Host the AfroEval console on Azure (run full evals incl. LaBSE)

**Date:** 2026-08-02
**Status:** Approved design, pre-implementation
**Supersedes:** the earlier "deploy the FastAPI backend + console calls it via API"
draft in this file's history — see Decision below.

## Problem

The Streamlit Cloud console runs the **entire** evaluation dispatcher **in-process**
(`render_run_evaluation` → a thread → `asyncio.run(dispatch_run(...))`). Streamlit Cloud
is memory-capped (~1 GB), requirements.txt-only, and ephemeral — so heavy runs struggle
and LaBSE (1.8 GB model + torch) cannot load at all. Evals launched from the Cloud console
record `multilingual_similarity` as `unavailable` and produce no divergence signal; full
runs only work locally out-of-band.

## Decision

**Move the whole console to Azure Container Apps** rather than keep it on Streamlit Cloud
and decouple execution via an API. Rationale (Dan's call, 2026-08-02):

- The heavy eval must run on Azure regardless — Streamlit Cloud cannot host LaBSE. So the
  only question is whether to *also* keep the console on Cloud (which then needs an API
  layer) or move it to Azure too.
- The console's auth is **Supabase Auth** (`auth.client.SupabaseAuthClient`), not Streamlit
  Cloud's access control — so it is fully portable; moving off Cloud costs no auth rework.
- With the console on Azure (memory + LaBSE present), it simply keeps running the eval
  **in-process as today** — so the API-decoupling layer is **not needed at all**. One
  platform, fewer moving parts, and it escapes every Streamlit Cloud constraint
  (memory ceiling, requirements.txt-only, ephemeral disk, reboot-after-push, sleep/wake).

Trade accepted: an always-on Azure container (~low-tens USD/mo) and owning the deploy loop,
vs. Streamlit Cloud's free zero-ops hosting.

## Goal

Run the existing Streamlit console on Azure Container Apps with `.[eval]` + LaBSE, so the
operator can launch a full evaluation (all evaluators, incl. LaBSE, divergence) from the
browser and see results — no separate backend, no console code rewrite.

## Non-goals

- Decoupling the UI from execution via an API / job queue (documented as the later upgrade
  if this ever becomes multi-user or runs get very heavy — then revisit the API-worker
  split). Not now.
- Changing scoring, evaluators, dispatch, or divergence logic.
- Changing auth (Supabase Auth stays).
- Removing the local `scripts/run_eval.py` / `.venv` path — it stays as a fallback.

## Architecture

```
Browser (operator)  ──HTTPS/WebSocket──▶  Azure Container Apps
                                          Streamlit console (container)
                                          • streamlit run console/app.py
                                          • .[eval] + CPU-torch + LaBSE baked in image
                                          • min-replicas = 1 (always warm; in-process
                                            eval thread never torn down; LaBSE resident)
                                          • Supabase Auth (login) + Supabase Postgres (data)
                                          • health probe → GET /_stcore/health
                                                    │
                                                    ▼
                                          Supabase (Postgres) — unchanged
```

The console runs **unchanged**: `render_run_evaluation` still creates the Assessment + Run
and dispatches in-process — it just now has the RAM and LaBSE to complete a full run.

## Components

### A. Dockerfile (new) — the console image

- Base `python:3.12-slim`; system deps for scientific wheels.
- Install the project with the `[eval]` extra, using **CPU-only torch**
  (`--extra-index-url https://download.pytorch.org/whl/cpu`) — LaBSE runs on CPU.
- **Bake LaBSE into the image** at build (`SentenceTransformer('sentence-transformers/LaBSE')`
  with a fixed `HF_HOME`) — zero runtime download, deterministic deploys.
- `CMD`: `streamlit run console/app.py` with container-appropriate flags
  (`--server.port 8000 --server.address 0.0.0.0 --server.headless true`), and XSRF/CORS
  settings compatible with running behind Container Apps ingress.
- Layer order: deps + model (slow, stable) cached; only app-code layer rebuilds on iteration.
- `.dockerignore` excludes `.venv/`, `.git/`, `tests/`, `docs/`, caches; **keeps** `benchmarks/`
  and all app packages.

### B. Streamlit container config

- A `.streamlit/config.toml` (or CMD flags) for headless server, correct address/port, and
  ingress-compatible XSRF/CORS/websocket settings. Container Apps supports WebSockets (which
  Streamlit requires); confirm ingress transport during deploy.

### C. Azure Container Apps config

- Image in ACR; Container App with **min-replicas = 1** (always warm — the in-process eval
  thread is never torn down mid-run; LaBSE stays resident), external HTTPS ingress on port
  8000 with WebSocket support, ~1–2 vCPU / **4 GB** (LaBSE + torch resident ~2–2.5 GB).
- Liveness probe → `GET /_stcore/health` (Streamlit's health endpoint).
- Env/secrets (as Container App secrets): everything the console reads today —
  `DATABASE_URL`, `AFROEVAL_SECRET_KEY`, the Supabase Auth creds the login uses
  (e.g. `SUPABASE_URL` / `SUPABASE_ANON_KEY` — confirm exact names from `auth/client.py`),
  the Azure-judge creds (`AZURE_OPENAI_*`), `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` /
  `GEMINI_API_KEY`, and `HF_HOME` matching the Dockerfile. The app reads config from env
  via pydantic settings, so container env vars are sufficient (no `secrets.toml` needed;
  the existing `st.secrets.get(...)` sync is already wrapped in try/except and degrades to
  env vars).

### D. Deploy runbook (docs)

- Copy-paste `az` commands: `az acr build` (builds the image **remotely** — no local Docker),
  then `az containerapp create/update`. Runs under Dan's Azure subscription.

## Console code changes

**None expected.** The console already dispatches in-process; it just needs the runtime
environment. Confirm during implementation that: (a) config resolves from env vars when
`st.secrets` is absent (it does — the sync is try/except-wrapped and `get_settings()` reads
env), and (b) nothing hard-requires a Streamlit-Cloud-only feature. If a small config read
needs adjusting, that is the only code touched.

## Migrations

Unchanged: the schema is kept at head by the existing deploy-migrate workflow. The console
container just needs `DATABASE_URL`.

## Division of labor

- **Claude produces:** the Dockerfile, `.dockerignore`, the Streamlit container config, and
  the copy-paste `az` deploy runbook + env/secrets table. Plus any tiny config-read fix if
  one proves necessary.
- **Dan runs:** `az acr build` + `az containerapp` deploy (his subscription), sets the
  Container App secrets, points DNS/uses the Container App URL, and does the first run.

## Testing

- No unit-testable code is added (Dockerfile + docs + config). Guard rails: the full pytest
  suite stays green (nothing app-level changes), `import console.app` succeeds, and the
  real gate is a **post-deploy smoke run** from the browser: a run completes,
  `multilingual_similarity` scores (not `unavailable`), divergence populates, scorecard
  renders.

## Cost

One small always-on Container Apps instance (~4 GB) — roughly low-tens USD/month; ACR
storage for a ~3 GB image. No per-run compute beyond the eval's own API calls.

## Rollout

1. Build + push the image (ACR); create the Container App with secrets + WebSocket ingress;
   confirm `GET /_stcore/health` and that login works.
2. Smoke run from the browser; confirm LaBSE + divergence populate and the scorecard renders.
3. Keep the Streamlit Cloud deployment available as a **fallback** during cutover (it can be
   retired once Azure is proven). `scripts/run_eval.py` in `.venv` remains a fallback too.

## Open questions (resolve during implementation)

1. **Exact Supabase Auth env-var names** — read from `auth/client.py`; include them in the
   runbook's secrets table.
2. **Streamlit ingress/XSRF** — confirm the minimal `config.toml` that works behind Container
   Apps WebSocket ingress (headless, address, and whether XSRF/CORS need relaxing).
3. **Cutover** — DNS/custom domain vs the default Container App URL; retire Cloud or keep as
   fallback (leaning keep-as-fallback initially).
