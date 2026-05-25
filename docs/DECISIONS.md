# Architecture Decisions

Documented shortcuts and design choices with explicit replacement triggers.
A shortcut with a written exit plan is a decision; an undocumented one is debt.

---

## ADR-001: Streamlit for Operator Console

**Decision:** Use Streamlit instead of a React/Next.js frontend.

**Reason:** Founder-executable with zero frontend engineering budget in the MVP. The console is
used by operators, not end customers. Speed of iteration matters more than UI polish.

**Replacement trigger:** Recurring revenue (>$50K ARR) or a multi-tenant need.

---

## ADR-002: PostgreSQL (managed) as primary database

**Decision:** PostgreSQL via Azure Database for PostgreSQL Flexible Server.

**Reason:** Relational structure maps cleanly to benchmark items, runs, and metric results.
Managed service eliminates ops burden. SQLModel gives us Pydantic + SQLAlchemy without ORM friction.

**Replacement trigger:** Time-series workload for monitoring (add TimescaleDB extension or InfluxDB).

---

## ADR-003: FastAPI background tasks instead of Celery/RQ

**Decision:** Use FastAPI `BackgroundTasks` for evaluation dispatch in the MVP.

**Reason:** Zero infrastructure overhead. No Redis or worker process to manage. Adequate for
single-operator MVP with one concurrent run at a time.

**Replacement trigger:** >10 concurrent assessment runs, or a queued backlog in production.

---

## ADR-004: WeasyPrint for PDF generation

**Decision:** WeasyPrint renders HTML/CSS to PDF for the scorecard generator.

**Reason:** Open-source, Python-native, supports the HTML/CSS template the designer will produce.
No paid API or service dependency.

**Replacement trigger:** If WeasyPrint cannot render the brand template correctly, fall back to ReportLab.

---

## ADR-005: Label Studio Community Edition for HITL

**Decision:** Label Studio CE for the SME benchmark validation workflow.

**Reason:** Free, self-hosted, supports JSONL import/export, configurable annotation interface.
No per-seat cost for the SME network.

**Replacement trigger:** SME network >20 people or need for advanced IRR tooling.

---

## ADR-006: Africa Intelligence Layer stays proprietary

**Decision:** AIL evaluators are NOT open-sourced, even when the methodology is published.

**Reason:** The methodology (dimensions, weights, rubric structure) can be published to build the
standard. Running it credibly requires the benchmark library, adjudicated rubric content, and
calibration data — those stay proprietary. Transparency builds trust; inputs stay the moat.

**Never change this decision without founder sign-off.**
