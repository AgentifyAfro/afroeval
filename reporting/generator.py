"""
AfroEval Scorecard™ report generator.

Produces two artefacts per completed Run:
  - <output_dir>/<run_id>.pdf  — branded PDF scorecard (ReportLab)
  - <output_dir>/<run_id>.json — machine-readable JSON snapshot

ADR-004: WeasyPrint (HTML→PDF) was the original plan but cannot load its
native GTK/Pango dependencies on Windows. ReportLab is the documented
fallback ("Replacement trigger: If WeasyPrint cannot render the brand
template correctly, fall back to ReportLab").

Usage:
    from reporting.generator import generate_scorecard_pdf, generate_scorecard_json
    pdf_path  = generate_scorecard_pdf(scorecard, run, assessment)
    json_path = generate_scorecard_json(scorecard, run, assessment)
"""

from __future__ import annotations

import enum
import io
import json
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

# ── AgentifyAfro brand palette (agentifyafro-brand-guidelines.md, Section 5) ──
PURPLE     = colors.HexColor("#7C3AED")
BLUE       = colors.HexColor("#4169E1")
CYAN       = colors.HexColor("#00CFFF")
WHITE      = colors.white
CHARCOAL   = colors.HexColor("#1A1A24")   # near-black wordmark / header fill
NEAR_BLACK = colors.HexColor("#0A0A0F")
SLATE      = colors.HexColor("#6B7280")   # secondary text / captions
LIGHT_GRAY = colors.HexColor("#E5E7EB")   # hairlines / borders
OFF_WHITE  = colors.HexColor("#F8F9FB")   # document canvas (print-heavy report)

SUCCESS = colors.HexColor("#10B981")
WARNING = colors.HexColor("#F59E0B")
ERROR   = colors.HexColor("#EF4444")

SUCCESS_TINT = colors.HexColor("#E7F8F1")
ERROR_TINT   = colors.HexColor("#FDECEC")

# ── Verdict colours/icons (VerdictBand values → functional status colours) ───
_VERDICT_COLOUR = {
    "Deployment-Ready": SUCCESS,
    "Conditional":      WARNING,
    "Not-Ready":        ERROR,
    "High-Risk":        ERROR,
}
_VERDICT_ICON = {
    "Deployment-Ready": "✓",
    "Conditional":      "⚠",
    "Not-Ready":        "✗",
    "High-Risk":        "⛔",
}

# Brand mark asset — cropped + alpha-keyed from assets/agentifyafro-logo.png.
# Never recreate the mark; if this file is missing, layouts fall back to text-only.
_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_LOGO_MARK = _ASSETS_DIR / "agentifyafro-mark.png"
_MARK_ASPECT = 261 / 283  # width / height of the cropped mark asset

# Default output dir — sibling of this file's parent package, inside project root
_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output" / "scorecards"


# ── Public API ────────────────────────────────────────────────────────────────

def generate_scorecard_pdf(
    scorecard,        # db.models.Scorecard
    run,              # db.models.Run
    assessment,       # db.models.Assessment
    output_dir: str | Path | None = None,
) -> str:
    """Generate the PDF scorecard. Returns the absolute path of the created file."""
    out = _ensure_output_dir(output_dir)
    pdf_path = out / f"{run.id}.pdf"
    _build_pdf(scorecard, run, assessment, pdf_path)
    return str(pdf_path)


def generate_scorecard_pdf_bytes(scorecard, run, assessment) -> bytes:
    """Build the PDF straight into memory — no disk write, no cached path to go
    stale. Scorecard/Run/Assessment rows in Postgres are the only durable state
    this needs, so it survives restarts/redeploys where local disk doesn't.
    """
    buf = io.BytesIO()
    _build_pdf(scorecard, run, assessment, buf)
    return buf.getvalue()


def generate_scorecard_json(
    scorecard,
    run,
    assessment,
    output_dir: str | Path | None = None,
) -> str:
    """Serialise the scorecard to a JSON snapshot. Returns absolute path."""
    out = _ensure_output_dir(output_dir)
    json_path = out / f"{run.id}.json"
    payload = _build_json_payload(scorecard, run, assessment)
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(json_path)


# ── PDF internals ─────────────────────────────────────────────────────────────

def _ensure_output_dir(output_dir: str | Path | None) -> Path:
    out = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


def _verdict_str(verdict) -> str:
    """scorecard.verdict may arrive as a VerdictBand enum member or a plain str.

    Enum.__str__ (even on a str-subclassed Enum) renders "VerdictBand.CONDITIONAL"
    instead of "Conditional" — always resolve to the underlying value for display.
    """
    return verdict.value if isinstance(verdict, enum.Enum) else str(verdict)


def _styles():
    base = getSampleStyleSheet()
    return {
        "wordmark": ParagraphStyle(
            "afro_wordmark", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=CHARCOAL,
            alignment=TA_LEFT,
        ),
        "title": ParagraphStyle(
            "afro_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=CHARCOAL,
            alignment=TA_CENTER, spaceBefore=2, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "afro_subtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=10, leading=13, textColor=SLATE,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "score_hero": ParagraphStyle(
            "afro_score_hero", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=48, leading=58, textColor=PURPLE,
            alignment=TA_CENTER, spaceBefore=6, spaceAfter=2,
        ),
        "verdict_label": ParagraphStyle(
            "afro_verdict_label", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=14, leading=18,
            alignment=TA_CENTER, spaceBefore=2, spaceAfter=4,
        ),
        "section_head": ParagraphStyle(
            "afro_section_head", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=PURPLE,
            spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "afro_body", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, leading=13, textColor=CHARCOAL,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "afro_meta", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, leading=11, textColor=SLATE,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "packs": ParagraphStyle(
            "afro_packs", parent=base["Normal"],
            fontName="Helvetica", fontSize=7.5, leading=11, textColor=SLATE,
            alignment=TA_LEFT, spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "afro_small", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, leading=11, textColor=CHARCOAL,
            spaceAfter=2,
        ),
    }


def _build_pdf(scorecard, run, assessment, out: Path | io.BytesIO) -> None:
    s = _styles()
    doc = SimpleDocTemplate(
        str(out) if isinstance(out, Path) else out,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.95 * inch,
        bottomMargin=0.75 * inch,
        title=f"AfroEval Scorecard™ — {assessment.name}",
        author="AgentifyAfro.ai",
    )

    story = []
    story += _cover_block(scorecard, run, assessment, s)
    story += _dimension_table(scorecard, s)
    if scorecard.remediation_roadmap:
        story += _remediation_section(scorecard, s)
    if scorecard.failing_examples:
        story += _failing_section(scorecard, s)
    story += _footer_block(scorecard, run, s)

    doc.build(story, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)


def _lerp_color(c1, c2, t: float):
    return colors.Color(
        c1.red + (c2.red - c1.red) * t,
        c1.green + (c2.green - c1.green) * t,
        c1.blue + (c2.blue - c1.blue) * t,
    )


def _draw_gradient_bar(canvas, x, y, width, height, steps: int = 120):
    """Draw the signature purple→blue→cyan gradient as adjacent thin rects —
    ReportLab's pdfgen canvas has no native linear-gradient fill for plain rects.
    """
    seg_w = width / steps
    for i in range(steps):
        t = i / (steps - 1)
        c = _lerp_color(PURPLE, BLUE, t / 0.5) if t < 0.5 else _lerp_color(BLUE, CYAN, (t - 0.5) / 0.5)
        canvas.setFillColor(c)
        canvas.rect(x + i * seg_w, y, seg_w + 0.5, height, fill=1, stroke=0)


def _draw_page_chrome(canvas, doc):
    """Header/footer chrome drawn on every page via canvas (outside flowable flow)."""
    w, h = letter
    canvas.saveState()

    # Document canvas — off-white, per brand guideline 7.1 for print-heavy reports
    canvas.setFillColor(OFF_WHITE)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Top bar (dark — signature presentation per guideline 4.3)
    bar_h = 0.55 * inch
    canvas.setFillColor(NEAR_BLACK)
    canvas.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)
    _draw_gradient_bar(canvas, 0, h - bar_h - 2, w, 2)

    text_x = 0.75 * inch
    if _LOGO_MARK.exists():
        mark_h = 0.3 * inch
        mark_w = mark_h * _MARK_ASPECT
        canvas.drawImage(
            str(_LOGO_MARK),
            0.75 * inch, h - bar_h / 2 - mark_h / 2,
            width=mark_w, height=mark_h,
            preserveAspectRatio=True, mask="auto",
        )
        text_x = 0.75 * inch + mark_w + 0.12 * inch

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(text_x, h - bar_h / 2 - 3.5, "AfroEval Scorecard™")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(LIGHT_GRAY)
    canvas.drawRightString(w - 0.75 * inch, h - bar_h / 2 - 3.5, "AgentifyAfro.ai · Confidential")

    # Bottom bar
    bottom_h = 0.35 * inch
    canvas.setFillColor(NEAR_BLACK)
    canvas.rect(0, 0, w, bottom_h, fill=1, stroke=0)
    canvas.setFillColor(LIGHT_GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, bottom_h / 2 - 3, "© 2026 AgentifyAfro.ai")
    canvas.drawCentredString(w / 2, bottom_h / 2 - 3, "Africa-first AI evaluation")
    canvas.drawRightString(w - 0.75 * inch, bottom_h / 2 - 3, f"Page {doc.page}")

    canvas.restoreState()


def _cover_block(scorecard, run, assessment, s):
    verdict = _verdict_str(scorecard.verdict)
    verdict_colour = _VERDICT_COLOUR.get(verdict, CHARCOAL)
    verdict_icon   = _VERDICT_ICON.get(verdict, "")
    _run_ts = run.completed_at or getattr(run, "started_at", None) or getattr(run, "created_at", None)
    run_date = _run_ts.strftime("%B %d, %Y") if _run_ts else "—"

    story = [Spacer(1, 0.1 * inch)]

    # Lockup: approved mark asset + real wordmark text (black-on-light per
    # guideline 4.3 — the supplied asset's white wordmark only works on dark).
    if _LOGO_MARK.exists():
        mark_h = 0.3 * inch
        mark_w = mark_h * _MARK_ASPECT
        logo_row = Table(
            [[RLImage(str(_LOGO_MARK), width=mark_w, height=mark_h), Paragraph("AgentifyAfro.ai", s["wordmark"])]],
            colWidths=[mark_w + 0.1 * inch, 2.2 * inch],
            hAlign="CENTER",
        )
        logo_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(logo_row)
        story.append(Spacer(1, 0.18 * inch))

    story.append(Paragraph("AfroEval Scorecard™", s["title"]))
    story.append(Paragraph(assessment.name, s["subtitle"]))
    story.append(Spacer(1, 0.12 * inch))
    story.append(HRFlowable(width="100%", thickness=0.75, color=LIGHT_GRAY, spaceAfter=0.15 * inch))

    # Metadata row — short fields only; long lists never belong in a fixed-width cell
    meta_data = [[
        Paragraph(f"<b>MODEL</b><br/>{assessment.model_identifier}", s["meta"]),
        Paragraph(f"<b>PROVIDER</b><br/>{assessment.model_provider}", s["meta"]),
        Paragraph(f"<b>DATE</b><br/>{run_date}", s["meta"]),
        Paragraph(f"<b>METHODOLOGY</b><br/>{scorecard.methodology_version}", s["meta"]),
    ]]
    meta_tbl = Table(meta_data, colWidths=[1.6 * inch] * 4)
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX",        (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_tbl)

    # Benchmark packs — wrapped list below the table, never crammed into a cell
    packs = [p.strip() for p in (scorecard.benchmark_pack_version or "").split(",") if p.strip()]
    if packs:
        story.append(Spacer(1, 0.08 * inch))
        story.append(Paragraph(
            f"<b>BENCHMARK PACKS ({len(packs)})</b>&nbsp;&nbsp;" + " · ".join(packs),
            s["packs"],
        ))

    story.append(Spacer(1, 0.3 * inch))

    # Composite score hero
    story.append(Paragraph(f"{scorecard.composite_score:.1f}", s["score_hero"]))

    verdict_label_style = ParagraphStyle(
        "verdict_dynamic", parent=s["verdict_label"], textColor=verdict_colour,
    )
    story.append(Paragraph(f"{verdict_icon}  {verdict}", verdict_label_style))

    confidence_display = "Standard Confidence" if scorecard.confidence_flag == "standard" else "⚠ Low Coverage"
    story.append(Paragraph(confidence_display, s["meta"]))
    if scorecard.safety_unverified:
        story.append(Paragraph("⚠ Safety Not Verified — no applicable safety items in this run", s["meta"]))
    if scorecard.african_fabrication_detected:
        story.append(Paragraph(
            "⚠ African Fabrication Detected — the response fabricated an Africa-specific "
            "entity (operator, institution, place or currency) on at least one item. "
            "See the flagged items for the triggering marker.",
            s["meta"],
        ))
    story.append(Spacer(1, 0.15 * inch))

    story.append(HRFlowable(width="100%", thickness=0.75, color=LIGHT_GRAY, spaceAfter=0.1 * inch))
    return story


def _dimension_table(scorecard, s):
    story = [Paragraph("Dimension Scores", s["section_head"])]

    dim_weights = scorecard.dimension_weights or {}
    dim_scores  = scorecard.dimension_scores  or {}

    dims_sorted = sorted(
        dim_weights.keys(),
        key=lambda d: dim_weights.get(d, 0),
        reverse=True,
    )

    header = ["Dimension", "Weight", "Score / 100", "Status"]
    rows = [header]
    for dim in dims_sorted:
        score  = dim_scores.get(dim, 0.0)
        weight = dim_weights.get(dim, 0.0)
        status = "✓ Pass" if score >= 60 else "✗ Below 60"
        rows.append([
            dim.replace("_", " ").title(),
            f"{weight:.0%}",
            f"{score:.1f}",
            status,
        ])

    col_widths = [2.8 * inch, 0.8 * inch, 1.1 * inch, 1.3 * inch]
    tbl = Table(rows, colWidths=col_widths)

    style_cmds = [
        ("BACKGROUND",   (0, 0), (-1, 0), CHARCOAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("GRID",         (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [OFF_WHITE, WHITE]),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
    ]
    # Colour status column cells individually
    for i, dim in enumerate(dims_sorted, start=1):
        score = dim_scores.get(dim, 0.0)
        cell_colour = SUCCESS_TINT if score >= 60 else ERROR_TINT
        style_cmds.append(("BACKGROUND", (3, i), (3, i), cell_colour))

    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)
    return story


def _remediation_section(scorecard, s):
    story = [Spacer(1, 0.1 * inch), Paragraph("Remediation Roadmap", s["section_head"])]
    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    roadmap = sorted(
        scorecard.remediation_roadmap,
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 2),
    )
    for item in roadmap:
        p = item.get("priority", "medium")
        dim = item.get("dimension", "").replace("_", " ").title()
        score = item.get("current_score", "")
        effort = item.get("estimated_effort", "")
        rec = item.get("recommendation", "")
        icon = priority_icon.get(p, "•")

        story.append(Paragraph(
            f"<b>{icon} [{p.upper()}] {dim}</b>  —  Score: {score:.1f}  |  Effort: {effort}",
            s["body"],
        ))
        story.append(Paragraph(rec, s["small"]))
        story.append(Spacer(1, 0.06 * inch))
    return story


def _failing_section(scorecard, s):
    story = [Spacer(1, 0.05 * inch), Paragraph("Failing Dimensions (below 60)", s["section_head"])]
    for ex in scorecard.failing_examples:
        dim   = ex.get("dimension", "").replace("_", " ").title()
        score = ex.get("score", "")
        note  = ex.get("note", "")
        story.append(Paragraph(f"<b>✗ {dim}</b>: {score:.1f} — {note}", s["small"]))
    return story


def _footer_block(scorecard, run, s):
    return [
        Spacer(1, 0.2 * inch),
        HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=0.1 * inch),
        Paragraph(
            f"Run ID: {run.id} | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            s["meta"],
        ),
        Paragraph(
            f"This scorecard is generated by AfroEval Scorecard™ {scorecard.methodology_version} — "
            "Africa-first AI evaluation. Confidential — Internal Use.",
            s["meta"],
        ),
    ]


# ── JSON internals ────────────────────────────────────────────────────────────

def _build_json_payload(scorecard, run, assessment) -> dict:
    return {
        "afroeval_version":      scorecard.methodology_version,
        "generated_at":          datetime.utcnow().isoformat() + "Z",
        "run": {
            "id":                str(run.id),
            "assessment_id":     str(run.assessment_id),
            "started_at":        run.started_at.isoformat() if run.started_at else None,
            "completed_at":      run.completed_at.isoformat() if run.completed_at else None,
        },
        "assessment": {
            "id":                str(assessment.id),
            "name":              assessment.name,
            "model_provider":    assessment.model_provider,
            "model_identifier":  assessment.model_identifier,
            "benchmark_pack_ids": assessment.benchmark_pack_ids,
        },
        "scorecard": {
            "id":                    str(scorecard.id),
            "composite_score":       scorecard.composite_score,
            "verdict":               _verdict_str(scorecard.verdict),
            "confidence_flag":       scorecard.confidence_flag,
            "safety_unverified":     scorecard.safety_unverified,
            "african_fabrication_detected": scorecard.african_fabrication_detected,
            "benchmark_pack_version": scorecard.benchmark_pack_version,
            "dimension_scores":      scorecard.dimension_scores,
            "dimension_weights":     scorecard.dimension_weights,
            "failing_examples":      scorecard.failing_examples,
            "remediation_roadmap":   scorecard.remediation_roadmap,
        },
    }
