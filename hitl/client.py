"""
Thin REST client for the Azure-hosted Label Studio instance.

LABEL_STUDIO_API_KEY is a JWT *refresh* token (this LS version uses JWT auth,
not the old static API key). Access tokens expire in ~5 minutes; we cache one
per client instance and refresh only when it expires, avoiding a round-trip on
every paginated call.
"""

import time
import requests

from api.settings import get_settings

_TOKEN_TTL = 270  # refresh 30s before the 5-min expiry


class LabelStudioClient:
    def __init__(self, base_url: str | None = None, refresh_token: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.label_studio_url).rstrip("/")
        self.refresh_token = refresh_token or settings.label_studio_api_key
        if not self.refresh_token:
            raise ValueError("LABEL_STUDIO_API_KEY is not set in .env")
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0

    def _access_token(self) -> str:
        if self._cached_token and time.monotonic() < self._token_expiry:
            return self._cached_token
        resp = requests.post(
            f"{self.base_url}/api/token/refresh",
            json={"refresh": self.refresh_token},
            timeout=15,
        )
        resp.raise_for_status()
        self._cached_token = resp.json()["access"]
        self._token_expiry = time.monotonic() + _TOKEN_TTL
        return self._cached_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def find_project_by_title(self, title: str) -> dict | None:
        resp = requests.get(f"{self.base_url}/api/projects/", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        body = resp.json()
        projects = body["results"] if isinstance(body, dict) else body
        return next((p for p in projects if p["title"] == title), None)

    def create_project(self, title: str, label_config: str) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/projects/",
            headers=self._headers(),
            json={"title": title, "label_config": label_config},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_or_create_project(self, title: str, label_config: str) -> dict:
        existing = self.find_project_by_title(title)
        if existing is not None:
            return existing
        return self.create_project(title, label_config)

    def import_tasks(self, project_id: int, tasks: list[dict]) -> dict:
        """tasks: list of plain data dicts — each gets wrapped in {"data": ...} here."""
        resp = requests.post(
            f"{self.base_url}/api/projects/{project_id}/import",
            headers=self._headers(),
            json=[{"data": t} for t in tasks],
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, project_id: int, page_size: int = 200) -> list[dict]:
        """All tasks for a project (not just annotated ones), paginated."""
        tasks: list[dict] = []
        page = 1
        while True:
            resp = requests.get(
                f"{self.base_url}/api/tasks/",
                headers=self._headers(),
                params={"project": project_id, "page": page, "page_size": page_size},
                timeout=30,
            )
            # Label Studio returns 404 for a page past the last one (so a task
            # count that is an exact multiple of page_size triggers a spurious
            # 404 on the next page). Treat that as the end of pagination.
            if resp.status_code == 404 and page > 1:
                break
            resp.raise_for_status()
            body = resp.json()
            batch = body["tasks"]
            tasks.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return tasks

    def delete_task(self, task_id: int) -> None:
        resp = requests.delete(f"{self.base_url}/api/tasks/{task_id}/", headers=self._headers(), timeout=15)
        resp.raise_for_status()

    def update_task_data(self, task_id: int, data: dict) -> dict:
        """Replaces a task's `data` dict entirely (send the full merged dict, not just changed keys)."""
        resp = requests.patch(
            f"{self.base_url}/api/tasks/{task_id}/",
            headers=self._headers(),
            json={"data": data},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def list_users(self) -> list[dict]:
        resp = requests.get(f"{self.base_url}/api/users/", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        body = resp.json()
        return body["results"] if isinstance(body, dict) else body

    def export_annotated_tasks(self, project_id: int) -> list[dict]:
        resp = requests.get(
            f"{self.base_url}/api/projects/{project_id}/export",
            headers=self._headers(),
            params={"exportType": "JSON"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
