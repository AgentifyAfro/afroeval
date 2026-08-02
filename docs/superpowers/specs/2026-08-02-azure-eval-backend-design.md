# Design — Azure eval backend (run full evals, incl. LaBSE, from the Cloud console)

**Date:** 2026-08-02
**Status:** Approved design, pre-implementation
**Author:** Dan Haile (with Claude)

## Problem

The Streamlit Cloud console runs the **entire** evaluation dispatcher **in-process**
(`render_run_evaluation` → a thread → `asyncio.run(dispatch_run(...))`,
`console/app.py`). Streamlit Cloud is memory-capped (~1 GB), requirements.txt-only,
and ephemeral — so heavy runs already struggle there, and LaBSE (1.8 GB model + torch)
cannot load at all. Result: evals kicked off from the Cloud console record
`multilingual_similarity` as `unavailable` and produce no judge-divergence signal;
full runs are only reliable when run locally out-of-band (`scripts/run_eval.py` in
`.venv`). The operator cannot run a complete eval — with LaBSE — from the cloud.

## Goal

Kick off a full evaluation (all evaluators, **including LaBSE**) from the Cloud
console, with execution running on a backend that has the resources to host it, and
results appearing in the console as they do today.

## Non-goals

- A job queue / horizontal scale (documented as the later upgrade; one run at a time
  is fine for a single operator now).
- Changing scoring, evaluators, or the divergence logic.
- Replacing the local `scripts/run_eval.py` / `.venv` path — it stays, unchanged.
- Moving the console itself off Streamlit Cloud (it stays; it just becomes a thin client).

## Architecture

```
Streamlit Cloud console (thin client)
   │  POST /v1/runs {assessment_id}      (HTTPS + X-API-Key)
   ▼
Azure Container Apps — FastAPI worker (api.main:app)
   • min-replicas = 1 (always warm)  → background eval tasks never torn down;
     LaBSE stays resident between runs
   • image bakes in .[eval] + CPU-only torch + LaBSE (pre-downloaded at build)
   • POST /v1/runs creates the Run + dispatch_run() in a BackgroundTask →
     runs the FULL dispatcher (all evaluators incl. LaBSE) → writes Supabase
   • liveness/health probe → GET /v1/health   (already exists)
   ▲
   │  console polls Supabase for status + scorecard (UNCHANGED — it already
   │  reads runs/scorecards straight from Postgres)
```

**Key insight:** the FastAPI backend already implements this pattern. `POST /v1/runs`
(`api/v1/routes/runs.py`) takes a `RunCreate {assessment_id}`, creates the Run, and
`background_tasks.add_task(_execute_run, run_id)` → `dispatch_run`. It is simply not
deployed anywhere (no Dockerfile; `docker-compose.yml` is local-only Postgres +
Label Studio). This design deploys it and points the console at it.

## Components

### A. Dockerfile (new)

- Base `python:3.12-slim`.
- Install the project with the `[eval]` extra, using a **CPU-only torch** index
  (`--extra-index-url https://download.pytorch.org/whl/cpu`) to avoid the multi-GB CUDA
  wheels — LaBSE runs on CPU.
- **Bake LaBSE into the image**: a build step
  `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/LaBSE')"`
  with a fixed `HF_HOME`/cache path, so there is **zero runtime download** and every
  deploy is deterministic.
- `CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
- Order layers so deps + model (slow, stable) are cached and only the app-code layer
  rebuilds on iteration.
- Expected image size ~2.5–3.5 GB (torch + LaBSE); one-time-per-deploy cost, cached,
  never touches a run.

### B. Console change (`console/app.py` `render_run_evaluation`)

- Today it creates an Assessment row, creates a Run row, and runs `dispatch_run`
  in-process in a thread. Change to: create the Assessment (as today, direct DB write —
  the console has Supabase access), then **`POST {AFROEVAL_API_URL}/v1/runs`** with the
  `assessment_id` and the `X-API-Key` header. The API creates the Run and dispatches on
  Azure. **Remove** the in-process Run-create + thread (so there is no double Run and no
  Cloud-side execution).
- Everything downstream is unchanged: the console already polls Supabase
  (`load_runs_summary`, scorecards) for status and results.
- New Streamlit secrets: `AFROEVAL_API_URL` (the Container App HTTPS URL) and
  `AFROEVAL_API_KEY`.
- Degrade gracefully: if `AFROEVAL_API_URL` is unset, keep the current in-process path
  (so local `streamlit run` still works without the backend) and show a clear notice.

### C. Azure Container Apps config

- Image pushed to Azure Container Registry (ACR); Container App with
  **min-replicas = 1**, external HTTPS ingress, ~1–2 vCPU / **4 GB** (LaBSE + torch
  resident ~2–2.5 GB).
- Secrets/env: `DATABASE_URL` (Supabase session pooler), a **strong** `AFROEVAL_API_KEY`
  (NOT the `dev-secret-change-in-production` default), the Azure-judge creds
  (`AZURE_OPENAI_*`), and `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`, plus
  the `HF_HOME` cache path matching the Dockerfile.
- Liveness probe → `GET /v1/health`.

### D. Deploy runbook (docs)

- The exact copy-paste `az` commands: `az acr build` (builds the image **remotely** —
  no local Docker needed), then `az containerapp create/update`. The deploy runs under
  **Dan's** Azure subscription.

## Auth & security

- The endpoint is public HTTPS; access is gated by the `X-API-Key` header (the app's
  existing mechanism — confirm during implementation whether it is enforced by global
  middleware in `api/main.py` or needs a `Depends` on the write routes; if the latter,
  add it). Set a strong key in prod; store it as a Container App secret and a Streamlit
  secret.
- Consider (optional, later) restricting ingress or adding IP allowlisting.

## Migrations

- The worker reads/writes the same Supabase; the schema must be at head. This is already
  handled by the existing deploy-migrate workflow (`alembic upgrade head` on
  `db/migrations/**` changes). The worker just needs `DATABASE_URL`; it does not run
  migrations itself.

## Division of labor

- **Claude produces:** the Dockerfile, the `console/app.py` API-client change (+ graceful
  local fallback), the config/secrets documentation, and the copy-paste `az` deploy
  runbook. Plus any small API auth hardening if the write routes aren't already gated.
- **Dan runs:** the actual `az acr build` + `az containerapp` deploy (his Azure
  subscription), sets the Container App + Streamlit secrets, and does the first
  end-to-end run.

## Testing

- Local: `docker`-free — verify the console API-client path with the API running locally
  (`uvicorn api.main:app`), pointing `AFROEVAL_API_URL` at `http://localhost:8000`; a run
  triggered from the console executes via the API and LaBSE scores (since local `.venv`
  has it). Confirm the graceful fallback when `AFROEVAL_API_URL` is unset.
- Post-deploy: a smoke run from the Cloud console against the Azure API → run completes,
  `multilingual_similarity` scores (not `unavailable`), divergence populates, scorecard
  renders in the console.
- Keep the full pytest suite green; the console change is unit-tested where it is pure
  (the request-building helper), the DB/HTTP path guarded by the suite + import as usual.

## Cost

- One small always-on Container Apps instance (~4 GB) — roughly low tens of USD/month.
  ACR storage for a ~3 GB image. No per-run compute beyond the eval's own API calls.

## Rollout

1. Build + push the image (ACR), create the Container App with secrets, confirm
   `GET /v1/health`.
2. Set `AFROEVAL_API_URL` + `AFROEVAL_API_KEY` Streamlit secrets; reboot the console.
3. Smoke run from the console; confirm LaBSE + divergence populate.
4. The local `run_eval.py` path remains available throughout as a fallback.

## Open questions (resolve during planning)

1. **API-key enforcement location** — confirm whether `X-API-Key` is already enforced
   globally or must be added to the write routes; harden if needed.
2. **Assessment creation** — console writes the Assessment directly (current behavior,
   keep) vs going through `POST /v1/assessments`. Leaning keep-direct for minimal change.
3. **Run-status UX** — the console already polls Supabase; confirm the post-POST UX
   (spinner/redirect) reads cleanly with the API path.
