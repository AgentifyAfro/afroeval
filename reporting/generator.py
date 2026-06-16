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

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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

# ── Brand palette ─────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#0f3460")
CORAL  = colors.HexColor("#e94560")
SLATE  = colors.HexColor("#a8b2d8")
WHITE  = colors.white
NEAR_WHITE = colors.HexColor("#F4F6FB")
LIGHT_BLUE = colors.HexColor("#D9E6F7")
MID_GREY   = colors.HexColor("#CCCCCC")
TEXT_DARK  = colors.HexColor("#1a1a2e")

# ── Verdict colours ───────────────────────────────────────────────────────────
_VERDICT_COLOUR = {
    "Deployment-Ready": colors.HexColor("#1a7a4a"),
    "Conditional":      colors.HexColor("#d97706"),
    "Not-Ready":        colors.HexColor("#c05621"),
    "High-Risk":        CORAL,
}
_VERDICT_ICON = {
    "Deployment-Ready": "✓",
    "Conditional":      "⚠",
    "Not-Ready":        "✗",
    "High-Risk":        "⛔",
}

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


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "afro_title", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=22, textColor=NAVY,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "afro_subtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=10, textColor=SLATE,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "score_hero": ParagraphStyle(
            "afro_score_hero", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=48, textColor=NAVY,
            alignment=TA_CENTER, spaceAfter=0,
        ),
        "verdict_label": ParagraphStyle(
            "afro_verdict_label", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=14,
            alignment=TA_CENTER, spaceAfter=4,
        ),
        "section_head": ParagraphStyle(
            "afro_section_head", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=12, textColor=NAVY,
            spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "afro_body", parent=base["Normal"],
            fontName="Helvetica", fontSize=9, textColor=TEXT_DARK,
            spaceAfter=4, leading=13,
        ),
        "meta": ParagraphStyle(
            "afro_meta", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, textColor=SLATE,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "afro_small", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, textColor=TEXT_DARK,
            spaceAfter=2, leading=11,
        ),
    }


def _build_pdf(scorecard, run, assessment, out_path: Path) -> None:
    s = _styles()
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
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


def _draw_page_chrome(canvas, doc):
    """Header/footer lines drawn on every page via canvas (outside flowable flow)."""
    w, h = letter
    canvas.saveState()

    # Top bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 0.45 * inch, w, 0.45 * inch, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0.75 * inch, h - 0.30 * inch, "AfroEval Scorecard™")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(w - 0.75 * inch, h - 0.30 * inch, "AgentifyAfro.ai | Confidential")

    # Bottom bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, w, 0.35 * inch, fill=1, stroke=0)
    canvas.setFillColor(CORAL)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, 0.12 * inch, f"© 2026 AgentifyAfro.ai")
    canvas.setFillColor(WHITE)
    canvas.drawCentredString(w / 2, 0.12 * inch, "Africa-first AI evaluation")
    canvas.drawRightString(w - 0.75 * inch, 0.12 * inch, f"Page {doc.page}")

    canvas.restoreState()


def _cover_block(scorecard, run, assessment, s):
    verdict = scorecard.verdict
    verdict_colour = _VERDICT_COLOUR.get(verdict, TEXT_DARK)
    verdict_icon   = _VERDICT_ICON.get(verdict, "")
    _run_ts = run.completed_at or getattr(run, "started_at", None) or getattr(run, "created_at", None)
    run_date = _run_ts.strftime("%B %d, %Y") if _run_ts else "—"

    story = [Spacer(1, 0.3 * inch)]
    story.append(Paragraph("AfroEval Scorecard™", s["title"]))
    story.append(Paragraph(assessment.name, s["subtitle"]))
    story.append(Spacer(1, 0.15 * inch))

    # Metadata row
    meta_data = [
        [
            Paragraph(f"<b>Model</b><br/>{assessment.model_identifier}", s["meta"]),
            Paragraph(f"<b>Provider</b><br/>{assessment.model_provider}", s["meta"]),
            Paragraph(f"<b>Pack(s)</b><br/>{scorecard.benchmark_pack_version}", s["meta"]),
            Paragraph(f"<b>Date</b><br/>{run_date}", s["meta"]),
            Paragraph(f"<b>Methodology</b><br/>{scorecard.methodology_version}", s["meta"]),
        ]
    ]
    meta_tbl = Table(meta_data, colWidths=[1.2 * inch] * 5)
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
        ("GRID",       (0, 0), (-1, -1), 0.5, MID_GREY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 0.25 * inch))

    # Composite score hero
    story.append(Paragraph(f"{scorecard.composite_score:.1f}", s["score_hero"]))

    verdict_label_style = ParagraphStyle(
        "verdict_dynamic", parent=s["verdict_label"], textColor=verdict_colour,
    )
    story.append(Paragraph(f"{verdict_icon}  {verdict}", verdict_label_style))

    confidence_display = "Standard Confidence" if scorecard.confidence_flag == "standard" else "⚠ Low Coverage"
    story.append(Paragraph(confidence_display, s["meta"]))
    story.append(Spacer(1, 0.1 * inch))

    story.append(HRFlowable(
        width="100%", thickness=2, color=CORAL, spaceAfter=0.15 * inch,
    ))
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
        ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("GRID",         (0, 0), (-1, -1), 0.5, MID_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [NEAR_WHITE, WHITE]),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
    ]
    # Colour status column cells individually
    for i, dim in enumerate(dims_sorted, start=1):
        score = dim_scores.get(dim, 0.0)
        cell_colour = colors.HexColor("#e6f4ea") if score >= 60 else colors.HexColor("#fce8e8")
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
        HRFlowable(width="100%", thickness=0.5, color=MID_GREY, spaceAfter=0.1 * inch),
        Paragraph(
            f"Run ID: {run.id} | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            s["meta"],
        ),
        Paragraph(
            "This scorecard is generated by AfroEval Scorecard™ v1.0 — Africa-first AI evaluation. "
            "Confidential — Internal Use.",
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
            "verdict":               scorecard.verdict,
            "confidence_flag":       scorecard.confidence_flag,
            "benchmark_pack_version": scorecard.benchmark_pack_version,
            "dimension_scores":      scorecard.dimension_scores,
            "dimension_weights":     scorecard.dimension_weights,
            "failing_examples":      scorecard.failing_examples,
            "remediation_roadmap":   scorecard.remediation_roadmap,
        },
    }
