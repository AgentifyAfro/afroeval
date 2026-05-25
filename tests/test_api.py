"""
API integration tests — Phase 0 / Week 1.

These tests run against the in-memory SQLite DB (via conftest.py fixtures).
They verify the scaffold is wired correctly before any evaluator logic is built.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "timestamp" in body


def test_create_assessment(client: TestClient):
    payload = {
        "name": "Test Assessment — GPT-4o Swahili Mobile Money",
        "model_provider": "openai",
        "model_identifier": "gpt-4o",
        "benchmark_pack_ids": ["mobile_money_sw_v1.0.0"],
        "config": {},
    }
    resp = client.post("/v1/assessments", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == payload["name"]
    assert body["model_provider"] == "openai"
    assert "id" in body


def test_list_assessments_empty(client: TestClient):
    resp = client.get("/v1/assessments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_assessment_not_found(client: TestClient):
    resp = client.get("/v1/assessments/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_create_and_fetch_assessment(client: TestClient):
    payload = {
        "name": "Fetch Test",
        "model_provider": "azure_openai",
        "model_identifier": "gpt-4o-deployment",
        "benchmark_pack_ids": [],
        "config": {},
    }
    create_resp = client.post("/v1/assessments", json=payload)
    assert create_resp.status_code == 201
    assessment_id = create_resp.json()["id"]

    get_resp = client.get(f"/v1/assessments/{assessment_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == assessment_id


def test_submit_run(client: TestClient):
    # Create assessment first
    assessment = client.post("/v1/assessments", json={
        "name": "Run Test Assessment",
        "model_provider": "jsonl_upload",
        "model_identifier": "upload",
        "benchmark_pack_ids": [],
        "config": {},
    }).json()

    resp = client.post("/v1/runs", json={"assessment_id": assessment["id"]})
    assert resp.status_code == 202
    run = resp.json()
    assert run["status"] in ("pending", "running", "completed", "failed")
    assert run["assessment_id"] == assessment["id"]


def test_run_not_found(client: TestClient):
    resp = client.get("/v1/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_scorecard_not_found_for_pending_run(client: TestClient):
    # Create assessment + run with no scorecard yet
    assessment = client.post("/v1/assessments", json={
        "name": "Scorecard Test",
        "model_provider": "openai",
        "model_identifier": "gpt-4o",
        "benchmark_pack_ids": [],
        "config": {},
    }).json()
    run = client.post("/v1/runs", json={"assessment_id": assessment["id"]}).json()

    resp = client.get(f"/v1/scorecards/{run['id']}")
    assert resp.status_code == 404
