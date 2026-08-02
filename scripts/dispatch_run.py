"""Dispatch an existing run in a fresh process (main thread).

The Streamlit console launches this as a subprocess for Run Evaluation instead of
running ``dispatch_run()`` in a background thread: some eval-stack libraries arm
signal-based timeouts, which only work in the *main thread of the main interpreter*
and raise "signal only works in main thread of the main interpreter" from Streamlit's
worker thread. A fresh process's main thread sidesteps that entirely — the same reason
the HITL actions already shell out via subprocess.

Usage:  python scripts/dispatch_run.py <run_id>
Reads config (DATABASE_URL, judge/provider keys, DEEPEVAL_*, …) from the environment,
which it inherits from the console process.
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: dispatch_run.py <run_id>", file=sys.stderr)
        raise SystemExit(2)
    run_id = sys.argv[1]

    from sqlmodel import Session

    from db.models import Run, RunStatus
    from db.session import get_engine

    try:
        from orchestration.dispatcher import dispatch_run
        asyncio.run(dispatch_run(run_id))
    except Exception as exc:  # noqa: BLE001 — persist the failure so the console can show it
        try:
            with Session(get_engine()) as s:
                run = s.get(Run, uuid.UUID(run_id))
                if run and run.status not in ("completed",):
                    run.status = RunStatus.FAILED
                    run.error_message = str(exc)
                    s.add(run)
                    s.commit()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
