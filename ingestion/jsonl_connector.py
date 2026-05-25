"""
JSONL upload connector — accepts pre-computed evaluation results.

Format: one JSON object per line with at minimum:
  {"item_id": "...", "prompt": "...", "model_output": "..."}
"""

import json
from pathlib import Path

from ingestion.base import ModelConnector, ModelResponseRaw


class JSONLConnector(ModelConnector):

    def __init__(self, jsonl_path: str | Path):
        self.jsonl_path = Path(jsonl_path)

    @property
    def provider_name(self) -> str:
        return "jsonl_upload"

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        if not self.jsonl_path.exists():
            raise FileNotFoundError(f"JSONL file not found: {self.jsonl_path}")

        # Build a lookup from item_id → row in the JSONL
        uploaded: dict[str, dict] = {}
        with self.jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if "item_id" in row:
                    uploaded[row["item_id"]] = row

        responses = []
        for item in items:
            item_id = item.get("id", "")
            if item_id in uploaded:
                row = uploaded[item_id]
                responses.append(ModelResponseRaw(
                    item_id=item_id,
                    prompt=item.get("prompt", ""),
                    raw_output=row.get("model_output", ""),
                    latency_ms=row.get("latency_ms"),
                    tokens_used=row.get("tokens_used"),
                    cost_usd=row.get("cost_usd"),
                ))
            else:
                # Item not in upload — record as empty response
                responses.append(ModelResponseRaw(
                    item_id=item_id,
                    prompt=item.get("prompt", ""),
                    raw_output="",
                ))
        return responses
