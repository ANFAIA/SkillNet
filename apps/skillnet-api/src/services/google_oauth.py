"""Sign in with Google: the OAuth 2.0 exchange and the account-matching rule.

Two separable halves live here on purpose.

*The protocol half* (`build_authorization_url`, `exchange_code`, `fetch_profile`)
speaks OAuth 2.0 authorization code with PKCE against Google. It never touches the
database.

*The policy half* (`resolve_account`) decides what a verified Google identity is
allowed to become in this deployment, and it is the part worth stating plainly:

- **Organization workspaces do not self-register.** Google can only authenticate
  someone an administrator already created. The identity is matched against
  existing accounts, and an unknown address is refused — no account is created.
  SkillNet is multi-tenant, so open registration would be a side door into a
  company's data for anyone who can create a Google account.
- **Individual workspaces do self-register**, because there is nobody to invite:
  the whole point of that mode is one person installing SkillNet for themselves.
- **An unverified email never matches anything.** Google says whether it has
  verified the address; without that guarantee an attacker can put any string in
  the field, and matching by email would hand them the matching account.

Matching happens on Google's `sub` claim first and the email only as the one-time
bridge that links an existing password account to its Google identity. `sub` is
stable and never reused; an email can be reassigned inside a Workspace domain.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.config import settings
from src.core.exceptions import AppError
from src.models import LearningProfile, UserRole, WorkspaceMode

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

#: Name of the short-lived cookie that carries the signed CSRF state and the PKCE
#: verifier between `/auth/google/authorize` and `/auth/google/callback`.
STATE_COOKIE_NAME = "skillnet_oauth_state"
#: A sign-in that takes longer than this is a stale or replayed callback.
STATE_MAX_AGE_SECONDS = 600

_SCOPES = "openid email profile"


class GoogleAuthError(AppError):
    """A refusal the SPA has to explain to the person in front of the browser.

    `reason` is a stable machine code (never a sentence) because the callback is a
    browser navigation: it travels as a query parameter and the SPA translates it.
    """

    def __init__(self, reason: str, message: str, status_code: int = 403) -> None:
        super().__init__(message=message, code="GOOGLE_AUTH_ERROR", status_code=status_code)
        self.reason = reason


@dataclass(frozen=True)
class GoogleProfile:
    """The claims we use out of Google's userinfo response."""

    sub: str
    email: str
    email_verified: bool
    full_name: str


def is_enabled() -> bool:
    """True when this deployment has Google credentials configured.

    Both halves are required: a client id with no secret cannot complete the code
    exchange, so advertising the button would only produce a dead end.
    """
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


# ---------------------------------------------------------------------------
# CSRF state + PKCE, carried in one signed cookie
# ---------------------------------------------------------------------------


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: bytes) -> str:
    return _b64(
        hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).digest()
    )


def new_state() -> tuple[str, str, str]:
    """Return ``(state, code_verifier, signed_cookie_value)`` for one sign-in attempt.

    The cookie is the second half of a double-submit check: Google echoes `state`
    back in the URL, and it only counts if it also matches the value the browser
    still holds. The PKCE verifier rides in the same cookie so the authorization
    code is useless to anyone who intercepts it without the browser.
    """
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    payload = json.dumps(
        {"state": state, "verifier": code_verifier, "ts": int(time.time())},
        separators=(",", ":"),
    ).encode()
    return state, code_verifier, f"{_b64(payload)}.{_sign(payload)}"


def read_state(cookie_value: str | None, returned_state: str | None) -> str:
    """Validate the callback against the cookie and return the PKCE verifier."""
    invalid = GoogleAuthError(
        "invalid_state",
        "This sign-in link is no longer valid. Please start again.",
        status_code=400,
    )
    if not cookie_value or not returned_state or "." not in cookie_value:
        raise invalid
    encoded, signature = cookie_value.rsplit(".", 1)
    try:
        payload = _unb64(encoded)
    except (ValueError, TypeError) as exc:  # malformed base64
        raise invalid from exc
    if not hmac.compare_digest(signature, _sign(payload)):
        raise invalid
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise invalid from exc
    if not hmac.compare_digest(str(data.get("state", "")), returned_state):
        raise invalid
    if int(time.time()) - int(data.get("ts", 0)) > STATE_MAX_AGE_SECONDS:
        raise invalid
    return str(data["verifier"])


# ---------------------------------------------------------------------------
# The protocol half
# ---------------------------------------------------------------------------


def build_authorization_url(*, state: str, code_verifier: str, redirect_uri: str) -> str:
    from urllib.parse import urlencode

    challenge = _b64(hashlib.sha256(code_verifier.encode()).digest())
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # No refresh token is wanted: SkillNet issues its own session and never
        # calls a Google API on the person's behalf afterwards.
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


async def exchange_code(*, code: str, code_verifier: str, redirect_uri: str) -> str:
    """Trade the authorization code for an access token. Returns the access token."""
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
    if response.status_code != 200:
        raise GoogleAuthError(
            "exchange_failed",
            "Google refused the sign-in request.",
            status_code=502,
        )
    token = response.json().get("access_token")
    if not token:
        raise GoogleAuthError(
            "exchange_failed", "Google returned no access token.", status_code=502
        )
    return str(token)


async def fetch_profile(access_token: str) -> GoogleProfile:
    """Read the claims from Google's userinfo endpoint.

    Deliberately a second server-to-server call rather than decoding the `id_token`
    locally. The response arrives over a TLS channel we opened to Google ourselves,
    which is exactly the condition under which OIDC allows skipping the JWT
    signature check — and it saves carrying a JWKS cache and a JWT library for one
    endpoint.
    """
    import httpx

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
        )
    if response.status_code != 200:
        raise GoogleAuthError(
            "profile_failed", "Could not read your Google profile.", status_code=502
        )
    return profile_from_claims(response.json())


def profile_from_claims(claims: dict[str, Any]) -> GoogleProfile:
    sub = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip().lower()
    if not sub or not email:
        raise GoogleAuthError(
            "profile_failed", "Google did not return an email address.", status_code=502
        )
    return GoogleProfile(
        sub=sub,
        email=email,
        # Google sends a real boolean here, but the claim is absent for some
        # account types; absent is not verified.
        email_verified=claims.get("email_verified") is True,
        full_name=str(claims.get("name") or "").strip() or email.split("@", 1)[0],
    )


# ---------------------------------------------------------------------------
# The policy half
# ---------------------------------------------------------------------------


class _AccountStore(Protocol):
    """The slice of `UserRepository` this policy needs. See `src.repositories.user_repo`."""

    async def get_by_google_sub(self, google_sub: str) -> Any: ...

    async def get_by_email(self, org_id: Any, email: str) -> Any: ...

    async def create(self, **kwargs: Any) -> Any: ...

    async def update(self, obj: Any, **kwargs: Any) -> Any: ...


async def resolve_account(*, store: _AccountStore, org: Any, profile: GoogleProfile) -> Any:
    """Turn a Google identity into the SkillNet account allowed to use it.

    Raises `GoogleAuthError` rather than returning None: every refusal has a
    distinct reason the person needs to read, and they are not interchangeable.
    """
    if not profile.email_verified:
        raise GoogleAuthError(
            "email_unverified",
            "Google has not verified this email address, so it cannot be used to "
            "sign in. Verify it with Google and try again.",
        )

    # 1. Already linked. The email is not consulted at all here — if it changed on
    #    Google's side, this is still the same person.
    linked = await store.get_by_google_sub(profile.sub)
    if linked is not None:
        return _ensure_active(linked)

    # 2. An existing account with that verified address: link it, once.
    existing = await store.get_by_email(org.id, profile.email)
    if existing is not None:
        if getattr(existing, "google_sub", None) not in (None, profile.sub):
            # Someone else's Google identity already owns this row. Refusing beats
            # silently rebinding an account to a different external identity.
            raise GoogleAuthError(
                "already_linked",
                "This account is already linked to a different Google identity.",
            )
        _ensure_active(existing)
        return await store.update(existing, google_sub=profile.sub)

    # 3. Nobody matches. Only an individual workspace may create the account.
    if org.workspace_mode is not WorkspaceMode.INDIVIDUAL:
        raise GoogleAuthError(
            "not_invited",
            "This Google account is not a member of this workspace. Ask an "
            "administrator to create your account first.",
        )
    return await store.create(
        org_id=org.id,
        email=profile.email,
        full_name=profile.full_name,
        # No password at all: this account signs in through Google only. A blank
        # string can never be produced by the hasher, so nothing verifies against
        # it — the password form stays closed until an admin resets it.
        hashed_password="",
        google_sub=profile.sub,
        # A newcomer to an individual workspace is a learner, not a second owner.
        # The owner created at first boot is matched by email in step 2 and keeps
        # their admin role; anybody arriving later gets the least privilege that
        # still lets them use the product.
        role=UserRole.EMPLOYEE,
        learning_profile=LearningProfile.STANDARD,
        is_active=True,
        is_verified=True,
    )


def _ensure_active(user: Any) -> Any:
    if getattr(user, "is_active", True) is False:
        raise GoogleAuthError(
            "inactive", "This account has been deactivated by an administrator."
        )
    return user
