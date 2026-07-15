#!/usr/bin/env python3
"""
AfroEval Scorecard™ — terminal runner.

Creates an assessment, triggers a run, polls until completion, and prints
a formatted scorecard to the terminal.

Usage:
    # Single pack
    python scripts/run_scorecard.py --packs customer_service_yo_v1.0.0

    # Multiple packs
    python scripts/run_scorecard.py --packs customer_service_yo_v1.0.0 --packs community_health_am_v1.0.0

    # Custom name + provider override
    python scripts/run_scorecard.py --packs safety_mixed_v1.0.0 --name "Safety smoke test" --provider anthropic

Prerequisites:
    The API server must be running:
        .venv\\Scripts\\python.exe -m uvicorn api.main:app --port 8001
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Vendor imports (httpx + dotenv are in .venv) ──────────────────────────────
try:
    import httpx
except ImportError:
    sys.exit("httpx not found — activate the .venv first.")

try:
    from dotenv import load_dotenv  # optional; swallowed if absent
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── ANSI palette ──────────────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_NAVY   = "\033[1;34m"   # bold blue  → header chrome
_CORAL  = "\033[1;31m"   # bold red   → brand accent / High-Risk
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"

_VERDICT_STYLE = {
    "Deployment-Ready": _GREEN,
    "Conditional":      _YELLOW,
    "Not-Ready":        _RED,
    "High-Risk":        _CORAL,
}
_VERDICT_ICON = {
    "Deployment-Ready": "✓",
    "Conditional":      "⚠",
    "Not-Ready":        "✗",
    "High-Risk":        "⛔",
}

_SPINNER = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hdr(client: httpx.Client, api_key: str) -> dict:
    return {"X-API-Key": api_key}


def _elapsed(start: float) -> str:
    s = int(time.time() - start)
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"


def _spin(msg: str) -> None:
    """Overwrite the current line with a spinner + message."""
    print(f"\r  {next(_SPINNER)}  {msg}          ", end="", flush=True)


def _clear_line() -> None:
    print("\r" + " " * 60 + "\r", end="", flush=True)


def _rule(char: str = "─", width: int = 52) -> str:
    return char * width


def _dim(text: str) -> str:
    return f"{_DIM}{text}{_RESET}"


# ── API calls ─────────────────────────────────────────────────────────────────

def create_assessment(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    name: str,
    provider: str,
    model: str,
    packs: list[str],
) -> dict:
    resp = client.post(
        f"{base_url}/v1/assessments",
        json={
            "name": name,
            "model_provider": provider,
            "model_identifier": model,
            "benchmark_pack_ids": packs,
        },
        headers=_hdr(client, api_key),
    )
    resp.raise_for_status()
    return resp.json()


def submit_run(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    assessment_id: str,
) -> dict:
    resp = client.post(
        f"{base_url}/v1/runs",
        json={"assessment_id": assessment_id},
        headers=_hdr(client, api_key),
    )
    resp.raise_for_status()
    return resp.json()


def poll_run(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    run_id: str,
    timeout: int = 600,
    interval: int = 3,
) -> dict:
    """Poll /v1/runs/{run_id} until terminal status or timeout. Returns final run dict."""
    start = time.time()
    terminal = {"completed", "failed"}

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            _clear_line()
            sys.exit(f"\n  Timed out after {timeout}s waiting for run {run_id}.")

        resp = client.get(
            f"{base_url}/v1/runs/{run_id}",
            headers=_hdr(client, api_key),
        )
        resp.raise_for_status()
        run = resp.json()
        status = run["status"]

        if status in terminal:
            _clear_line()
            return run

        _spin(f"Status: {status}  ({_elapsed(start)} elapsed)")
        time.sleep(interval)


def fetch_scorecard(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    run_id: str,
) -> dict:
    resp = client.get(
        f"{base_url}/v1/scorecards/{run_id}",
        headers=_hdr(client, api_key),
    )
    resp.raise_for_status()
    return resp.json()


# ── Terminal output ────────────────────────────────────────────────────────────

def _print_header() -> None:
    w = 52
    inner = "AfroEval Scorecard™"
    pad = (w - 2 - len(inner)) // 2
    print()
    print(f"  {_NAVY}╔{'═' * w}╗{_RESET}")
    print(f"  {_NAVY}║{' ' * pad}{inner}{' ' * (w - pad - len(inner))}║{_RESET}")
    print(f"  {_NAVY}╚{'═' * w}╝{_RESET}")
    print()


def _print_meta(assessment: dict, run: dict) -> None:
    def row(label: str, value: str) -> None:
        print(f"  {_DIM}{label:<16}{_RESET}{value}")

    row("Assessment", assessment["name"])
    row("Model", f"{assessment['model_identifier']}  {_dim('(' + assessment['model_provider'] + ')')}")
    row("Pack(s)", ", ".join(assessment["benchmark_pack_ids"]))
    row("Run ID", run["id"])
    if run.get("completed_at"):
        ts = run["completed_at"].replace("T", " ").split(".")[0]
        row("Completed", ts)
    print()


def _print_score_box(scorecard: dict) -> None:
    verdict   = scorecard["verdict"]
    score     = scorecard["composite_score"]
    style     = _VERDICT_STYLE.get(verdict, "")
    icon      = _VERDICT_ICON.get(verdict, "")
    conf      = scorecard.get("confidence_flag", "standard")
    conf_str  = "" if conf == "standard" else f"  {_YELLOW}⚠ Low Coverage{_RESET}"
    if scorecard.get("safety_unverified"):
        conf_str += f"  {_YELLOW}⚠ Safety Not Verified{_RESET}"

    score_str = f"{score:.1f} / 100"
    verdict_str = f"{icon}  {verdict}"

    box_content = f"  Composite Score   {_BOLD}{score_str}{_RESET}   {style}{_BOLD}{verdict_str}{_RESET}{conf_str}"
    rule = _rule("─", 52)

    print(f"  ┌{rule}┐")
    print(f"{box_content}")
    print(f"  └{rule}┘")
    print()


def _print_dimensions(scorecard: dict) -> None:
    dim_scores  = scorecard.get("dimension_scores", {})
    dim_weights = scorecard.get("dimension_weights", {})

    if not dim_scores:
        return

    print(f"  {_BOLD}Dimension Breakdown{_RESET}")
    print(f"  {_rule()}")

    # Sort by weight descending (same order as the PDF)
    dims = sorted(dim_scores.keys(), key=lambda d: dim_weights.get(d, 0), reverse=True)

    for dim in dims:
        score  = dim_scores[dim]
        weight = dim_weights.get(dim, 0.0)
        label  = dim.replace("_", " ").title()
        passed = score >= 60
        status = f"{_GREEN}✓ Pass{_RESET}" if passed else f"{_RED}✗ Below 60{_RESET}"
        score_col = f"{_GREEN}{score:5.1f}{_RESET}" if passed else f"{_RED}{score:5.1f}{_RESET}"

        print(f"  {label:<28}  {weight:>4.0%}   {score_col}   {status}")

    print()


def _print_remediation(scorecard: dict) -> None:
    roadmap = scorecard.get("remediation_roadmap") or []
    if not roadmap:
        return

    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    priority_order = {"high": 0, "medium": 1, "low": 2}
    roadmap = sorted(roadmap, key=lambda x: priority_order.get(x.get("priority", "low"), 2))

    print(f"  {_BOLD}Remediation Roadmap{_RESET}")
    print(f"  {_rule()}")

    for item in roadmap:
        p       = item.get("priority", "medium")
        dim     = item.get("dimension", "").replace("_", " ").title()
        rec     = item.get("recommendation", "")
        effort  = item.get("estimated_effort", "")
        icon    = priority_icon.get(p, "•")
        score   = item.get("current_score", "")
        score_s = f" — Score: {score:.1f}" if isinstance(score, (int, float)) else ""
        effort_s = f" | Effort: {effort}" if effort else ""

        print(f"  {icon} {_BOLD}[{p.upper()}]{_RESET} {dim}{score_s}{effort_s}")
        if rec:
            print(f"    {_DIM}{rec}{_RESET}")

    print()


def _print_artefacts(scorecard: dict) -> None:
    pdf  = scorecard.get("pdf_path")
    json = scorecard.get("json_path")
    if not pdf and not json:
        return

    print(f"  {_BOLD}Artefacts{_RESET}")
    print(f"  {_rule()}")
    if pdf:
        print(f"  {_CYAN}PDF {_RESET}  {pdf}")
    if json:
        print(f"  {_CYAN}JSON{_RESET}  {json}")
    print()


def print_scorecard(scorecard: dict, assessment: dict, run: dict) -> None:
    _print_header()
    _print_meta(assessment, run)
    _print_score_box(scorecard)
    _print_dimensions(scorecard)
    _print_remediation(scorecard)
    _print_artefacts(scorecard)


def print_failure(run: dict) -> None:
    _clear_line()
    msg = run.get("error_message") or "Unknown error"
    print(f"\n  {_CORAL}✗  Run failed{_RESET}")
    print(f"  {_DIM}{msg}{_RESET}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AfroEval Scorecard™ — run from the terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_scorecard.py --packs customer_service_yo_v1.0.0
  python scripts/run_scorecard.py --packs safety_mixed_v1.0.0 --name "Safety smoke test"
  python scripts/run_scorecard.py --packs pack1 --packs pack2 --provider anthropic
        """,
    )
    p.add_argument(
        "--packs", "-p",
        action="append",
        required=True,
        metavar="PACK_ID",
        help='Pack identifier(s), format: <name>_v<version>. Repeat for multiple packs.',
    )
    p.add_argument(
        "--name", "-n",
        default=None,
        help="Assessment name (default: auto-generated from model + timestamp)",
    )
    p.add_argument(
        "--provider",
        default="azure_openai",
        choices=["azure_openai", "openai", "anthropic"],
        help="Model provider (default: azure_openai)",
    )
    p.add_argument(
        "--model", "-m",
        default="gpt-4.1-mini",
        help="Model identifier / deployment name (default: gpt-4.1-mini)",
    )
    p.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="AfroEval API base URL (default: http://localhost:8001)",
    )
    p.add_argument(
        "--api-key",
        default="dev-secret-change-in-production",
        help="X-API-Key for the AfroEval API",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Poll timeout in seconds (default: 600)",
    )
    p.add_argument(
        "--poll-interval",
        type=int,
        default=3,
        help="Poll interval in seconds (default: 3)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Flatten comma-separated packs so both styles work:
    #   --packs pack1,pack2   and   --packs pack1 --packs pack2
    packs = [p.strip() for raw in args.packs for p in raw.split(",") if p.strip()]

    name = args.name or f"{args.model} @ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    print(f"\n  {_BOLD}AfroEval Scorecard™{_RESET}  —  starting run")
    print(f"  {_DIM}Provider: {args.provider}  |  Model: {args.model}{_RESET}")
    print(f"  {_DIM}Packs: {', '.join(packs)}{_RESET}\n")

    try:
        with httpx.Client(timeout=30) as client:

            # Step 1: create assessment
            print("  Creating assessment...", end="", flush=True)
            try:
                assessment = create_assessment(
                    client, args.base_url, args.api_key,
                    name, args.provider, args.model, packs,
                )
            except httpx.ConnectError:
                sys.exit(
                    f"\n\n  ✗  Cannot reach the API at {args.base_url}\n"
                    "     Start the server first:\n"
                    "     .venv\\Scripts\\python.exe -m uvicorn api.main:app --port 8001\n"
                )
            except httpx.HTTPStatusError as exc:
                sys.exit(f"\n\n  ✗  Assessment creation failed: {exc.response.status_code}\n"
                         f"     {exc.response.text}\n")

            print(f"\r  ✓  Assessment created  {_DIM}({assessment['id']}){_RESET}")

            # Step 2: submit run
            print("  Submitting run...", end="", flush=True)
            try:
                run_init = submit_run(client, args.base_url, args.api_key, assessment["id"])
            except httpx.HTTPStatusError as exc:
                sys.exit(f"\n\n  ✗  Run submission failed: {exc.response.status_code}\n"
                         f"     {exc.response.text}\n")

            run_id = run_init["id"]
            print(f"\r  ✓  Run submitted       {_DIM}({run_id}){_RESET}\n")

            # Step 3: poll
            run = poll_run(
                client, args.base_url, args.api_key,
                run_id, args.timeout, args.poll_interval,
            )

            if run["status"] != "completed":
                print_failure(run)
                sys.exit(1)

            print(f"  {_GREEN}✓  Run completed{_RESET}\n")

            # Step 4: fetch scorecard
            try:
                scorecard = fetch_scorecard(client, args.base_url, args.api_key, run_id)
            except httpx.HTTPStatusError as exc:
                sys.exit(f"\n  ✗  Could not fetch scorecard: {exc.response.status_code}\n"
                         f"     {exc.response.text}\n")

            print_scorecard(scorecard, assessment, run)

    except KeyboardInterrupt:
        _clear_line()
        print(f"\n  {_DIM}Interrupted.{_RESET}\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
