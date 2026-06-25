"""
Tests for auth/client.py — mocks the supabase client entirely, no network calls.
"""

from unittest.mock import MagicMock

import pytest
from supabase_auth.errors import AuthApiError

from auth.client import (
    AuthServiceUnavailableError,
    AuthUser,
    InvalidCredentialsError,
    SupabaseAuthClient,
)


def _client_with_fake_supabase(monkeypatch, fake_supabase) -> SupabaseAuthClient:
    monkeypatch.setattr("auth.client.create_client", lambda url, key: fake_supabase)
    return SupabaseAuthClient(url="https://example.supabase.co", anon_key="anon-key")


def test_sign_in_returns_auth_user_with_role(monkeypatch):
    fake_user = MagicMock(id="u1", email="admin@agentifyafro.ai", app_metadata={"role": "admin"})
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.return_value = MagicMock(user=fake_user)

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    result = client.sign_in("admin@agentifyafro.ai", "correct-password")

    assert result == AuthUser(id="u1", email="admin@agentifyafro.ai", role="admin")


def test_sign_in_defaults_role_to_none_when_no_app_metadata(monkeypatch):
    fake_user = MagicMock(id="u2", email="viewer@agentifyafro.ai", app_metadata={})
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.return_value = MagicMock(user=fake_user)

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    result = client.sign_in("viewer@agentifyafro.ai", "correct-password")

    assert result.role is None


def test_sign_in_raises_invalid_credentials_on_auth_api_error(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.side_effect = AuthApiError("Invalid login credentials", 400, "invalid_credentials")

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    with pytest.raises(InvalidCredentialsError):
        client.sign_in("viewer@agentifyafro.ai", "wrong-password")


def test_sign_in_raises_service_unavailable_on_other_errors(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.auth.sign_in_with_password.side_effect = ConnectionError("network down")

    client = _client_with_fake_supabase(monkeypatch, fake_supabase)
    with pytest.raises(AuthServiceUnavailableError):
        client.sign_in("viewer@agentifyafro.ai", "any-password")


def test_missing_url_raises_value_error():
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        SupabaseAuthClient(url="", anon_key="anon-key")


def test_missing_anon_key_raises_value_error():
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        SupabaseAuthClient(url="https://example.supabase.co", anon_key="")
