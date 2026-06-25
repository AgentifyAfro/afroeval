"""
Verify RLS is closing the public-table PostgREST exposure.

Hits the live PostgREST endpoint directly with the anon key and reports
whether model_responses rows are readable. Run before AND after applying
the RLS migration (see db/migrations/versions/dda5b8820ce4_enable_rls_public_tables.py)
to confirm the before/after behavior change.

Usage (from afroeval/):
    .\\.venv\\Scripts\\python.exe scripts/verify_rls_fix.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from api.settings import get_settings


def check_anon_access() -> None:
    settings = get_settings()
    url = f"{settings.supabase_url}/rest/v1/model_responses"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }
    resp = requests.get(url, headers=headers, params={"limit": 1}, timeout=15)
    resp.raise_for_status()
    rows = resp.json()
    if rows:
        print(f"EXPOSED: anon key can read {len(rows)} row(s) from model_responses — RLS is NOT blocking access.")
    else:
        print("CLOSED: anon key returned zero rows from model_responses — RLS is blocking access as expected.")


if __name__ == "__main__":
    check_anon_access()
