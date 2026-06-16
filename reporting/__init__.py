"""
Reporting module — AfroEval Scorecard™ PDF and JSON generator.

Uses ReportLab (pure Python, no native dependencies) per ADR-004 fallback:
WeasyPrint/HTML→PDF was the original plan but requires native GTK/Pango
libraries unavailable in this environment.
"""

from reporting.generator import generate_scorecard_json, generate_scorecard_pdf

__all__ = ["generate_scorecard_pdf", "generate_scorecard_json"]
