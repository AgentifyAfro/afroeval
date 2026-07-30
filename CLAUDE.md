# AfroEval — Claude Code Instructions

## Do NOT modify these files automatically

Files in `benchmarks/packs/*.jsonl` are **SME-validated benchmark data**.
They must never be rewritten, reformatted, or "simplified" by any automated tool or agent.
Each line is a carefully authored test case. Treat them as read-only unless the user explicitly asks to edit them.

## Running the project

```powershell
# Start server (from afroeval/)
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8001

# Run tests
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

## Key facts

- Venv: `.venv/` (Python 3.12) — has all dependencies including fairlearn, deepeval, ragas, openai
- DB: Supabase PostgreSQL (session pooler) — configured via DATABASE_URL in .env
- API key for local dev: `dev-secret-change-in-production` (X-API-Key header)
- Azure deployment: `gpt-4.1-mini` — credentials in .env (never commit .env)

## Console (Streamlit operator UI)

The operator console lives in `console/` and is deployed to Streamlit Cloud
(reboot-after-push — pushes don't hot-reload; a manual reboot is the real visual check).
Cannot be rendered headlessly, so verify UI changes by rebooting, not locally.

- **`console/app.py`** — main app: cached `load_*` data functions + one `render_*`
  function per view. Views: Run Evaluation, Run Scorecard, Provider Comparison,
  Language Comparison, SME Calibration, Pack Management, HITL Management.
- **`console/branding.py`** — the presentation layer (import helpers from here, don't
  inline CSS): `inject_brand_css()` (one master `<style>` block), `render_section_header`,
  `render_section_divider`, `render_kpi_row`, `render_scorecard_header`,
  `render_dimension_cards`, `render_comparison_bars`, `render_item_detail`,
  `render_detail_placeholder`, `render_callout`, `render_data_table`, `render_status_badge`.
  In `render_data_table`, **headers are escaped but row cells are trusted markup** (so badge
  HTML renders) — callers must `_esc` any free-form text placed in a cell.
- **`console/access.py`** — two-tier view gating (Category-1 = any viewer; Category-2 =
  admin/operator: Run Evaluation, Pack Management, HITL Management). **Never change gating,
  scoring, auth, or orchestration as part of a UI/brand change** — those passes are
  presentation-only unless explicitly asked otherwise.
- **`console/theme.py`** — WCAG-AA-tested palette; `tests/test_console_contrast.py` enforces
  contrast. Source colours from `theme.py`, not raw hexes that may fail AA on the card surface.
- **Design source of truth**: the approved preview mock (an HTML artifact). Pull exact CSS
  values from it rather than eyeballing. Its spaciousness comes from **layout/margins**
  (generous gaps, 2-per-row cards), not oversized fonts.
- **HITL Management** is a 3-tab Label Studio ops hub (Authoring / Validation / Calibration).
  Actions run existing `scripts/*.py` via subprocess (`_run_pipeline`); **writing actions
  default to dry-run**. Live LS/coverage data is best-effort and degrades gracefully when LS
  creds (Streamlit secrets) or the `item_validations` migration are absent.
- Tests: `tests/test_console_branding.py`, `test_console_contrast.py`, `test_console_access.py`.
