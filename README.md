# AfroEval Scorecard™

**Africa-first AI evaluation platform — AgentifyAfro.ai**

AfroEval evaluates AI systems against African language, cultural, fairness, hallucination, and deployment-readiness criteria, then generates a governance-grade scorecard.

> **Status:** Phase 0 / Week 1 — Project Foundation. MVP target: 16 weeks.

---

## Quick Start (local development)

### Prerequisites

- Python 3.11+
- PostgreSQL (or Docker — `docker compose up -d db`)
- Git

### 1. Environment setup

```bash
git clone <repo-url>
cd afroeval

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, OPENAI_API_KEY etc.
```

### 3. Seed benchmark packs (development data)

```bash
python scripts/seed_benchmarks.py
```

### 4. Run the API

```bash
uvicorn api.main:app --reload
# → http://localhost:8000/docs
```

### 5. Run the operator console

```bash
streamlit run console/app.py
# → http://localhost:8501
```

### 6. Run tests

```bash
pytest tests/ -v
```

---

## Repository Structure

```
afroeval/
├── api/              FastAPI service — versioned /v1 endpoints
│   └── v1/routes/    assessments, runs, scorecards, health
├── ingestion/        Model connectors: OpenAI, Azure OpenAI, JSONL upload
├── orchestration/    Job dispatch — wires ingestion → evaluators → scoring
├── evaluators/       Open-source metric wrappers (DeepEval, Ragas, Fairlearn)
├── ail/              Africa Intelligence Layer — proprietary evaluators (AIL)
├── scoring/          Composite scoring engine, verdict bands, confidence
├── benchmarks/       Benchmark loader, versioned JSONL packs
│   └── packs/        Pack files — never publish held-out splits
├── reporting/        Scorecard generator (HTML/CSS → PDF), JSON export
│   └── templates/    Jinja2 scorecard templates
├── console/          Streamlit operator console
├── hitl/             Label Studio integration — SME validation workflow
├── tests/            Unit tests + scoring regression harness
├── scripts/          CLI utilities (seed, migrate, export)
├── docs/             Architecture decisions, methodology spec
└── db/               SQLModel data models, Alembic migrations
```

---

## The Six AfroEval Dimensions

| Dimension | Weight | Measures |
|---|---|---|
| Language Performance | 25% | Accuracy & fluency in African languages |
| Cultural Appropriateness | 20% | Alignment with African cultural norms (AIL) |
| Hallucination Risk | 20% | Fabricated facts, African-specific probes |
| Bias & Fairness | 15% | Performance parity across cohorts |
| Code-Switching Quality | 10% | Sheng, Pidgin, mixed-language handling |
| Safety & Robustness | 10% | Harmful content, adversarial robustness |

**Verdict bands:** Deployment-Ready (80–100) · Conditional (60–79) · Not-Ready (40–59) · High-Risk (0–39)

---

## Module Contract

Every module follows one rule: contribute a **benchmark pack**, **evaluators**, and a **report section** — and consume shared services without reaching into another module's internals. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Build Roadmap

| Phase | Weeks | Status |
|---|---|---|
| Phase 0 — Foundation | 0–4 | **In progress** |
| Sprint 1 — Evaluation Core & Model Ingestion | 5–6 | Upcoming |
| Sprint 2 — Africa Intelligence Layer | 7–8 | Upcoming |
| Sprint 3 — Scoring Engine & Benchmark Integration | 9–10 | Upcoming |
| Sprint 4 — Scorecard Generator, Console & API | 11–12 | Upcoming |
| Sprint 5 — Integration, Alpha Pilots & Hardening | 13–14 | Upcoming |
| Sprint 6 — Beta Launch & Design Partners | 15–16 | Upcoming |

---

## Classification

Confidential — Internal Build Use. © AgentifyAfro.ai 2026.
The Africa Intelligence Layer is proprietary. See [docs/DECISIONS.md](docs/DECISIONS.md) ADR-006.
