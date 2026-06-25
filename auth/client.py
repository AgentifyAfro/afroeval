"""
Thin wrapper around supabase-py for console login.

Only sign-in/sign-out are needed here — account creation and role
assignment happen manually in the Supabase dashboard (invite-only,
admin-provisioned). See docs/superpowers/specs/2026-06-25-two-tier-auth-design.md.
"""

from dataclasses import dataclass

from supabase import Client, create_client
from supabase_auth.errors import AuthApiError

from api.settings import get_settings


class InvalidCredentialsError(Exception):
    """Raised when email/password don't match a Supabase Auth account."""


class AuthServiceUnavailableError(Exception):
    """Raised when Supabase Auth itself can't be reached."""


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    role: str | None


class SupabaseAuthClient:
    def __init__(self, url: str | None = None, anon_key: str | None = None):
        settings = get_settings()
        self.url = url if url is not None else settings.supabase_url
        self.anon_key = anon_key if anon_key is not None else settings.supabase_anon_key
        if not self.url or not self.anon_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
        self._client: Client = create_client(self.url, self.anon_key)

    def sign_in(self, email: str, password: str) -> AuthUser:
        try:
            resp = self._client.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError as exc:
            raise InvalidCredentialsError(str(exc)) from exc
        except Exception as exc:
            raise AuthServiceUnavailableError(str(exc)) from exc

        user = resp.user
        role = (user.app_metadata or {}).get("role")
        return AuthUser(id=user.id, email=user.email, role=role)

    def sign_out(self) -> None:
        self._client.auth.sign_out()
