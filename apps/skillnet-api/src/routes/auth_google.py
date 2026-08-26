"""Sign in with Google: the two browser-facing endpoints of the OAuth code flow.

`GET /auth/google/authorize` sends the browser to Google. `GET /auth/google/callback`
receives it back, turns the code into a verified identity, and — on success — issues
exactly the same session cookie the password login issues. There is no second kind
of session: once the cookie is set, nothing downstream knows or cares how it was
obtained.

Both endpoints 404 when the deployment has no Google credentials, so an unconfigured
instance exposes no half-working surface at all.

The policy that decides which identities are accepted lives in
`src/services/google_oauth.py`, not here. This module is transport.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from sqlalchemy import select

from src.auth.backend import get_database_strategy
from src.config import settings
from src.core.exceptions import AppError
from src.core.logging import get_logger
from src.deps.auth import auth_backend
from src.deps.db import DBSession
from src.models import Organization
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.user_repo import UserRepository
from src.services import google_oauth
from src.services.google_oauth import STATE_COOKIE_NAME, GoogleAuthError

logger = get_logger(__name__)

router = APIRouter(prefix="/auth/google", tags=["Auth"])


def _require_enabled() -> None:
    if not google_oauth.is_enabled():
        raise AppError(
            message="Google sign-in is not configured on this deployment",
            code="NOT_FOUND",
            status_code=404,
        )


def _redirect_uri(request: Request) -> str:
    """The callback URL, which has to match Google's registration character for character.

    Configured wins over derived: behind a reverse proxy the request's own host is
    whatever the proxy forwarded, which is exactly the value Google will reject.
    """
    if settings.GOOGLE_REDIRECT_URI:
        return settings.GOOGLE_REDIRECT_URI
    return str(request.url_for("google_callback"))


def _error_redirect(reason: str) -> RedirectResponse:
    """Send the browser back to the login screen with a machine-readable reason.

    A JSON error body would be correct for an API and useless here: the caller is a
    browser mid-navigation, and what it needs is a screen. The SPA translates the
    `google_error` code; the API never ships the sentence a person reads.
    """
    target = f"{settings.GOOGLE_LOGIN_ERROR_PATH}?{urlencode({'google_error': reason})}"
    response = RedirectResponse(url=target, status_code=303)
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return response


@router.get("/authorize", name="google_authorize")
async def google_authorize(request: Request) -> Response:
    """Start the flow: park the CSRF state and PKCE verifier, then hand off to Google."""
    _require_enabled()
    state, verifier, cookie_value = google_oauth.new_state()
    response = RedirectResponse(
        url=google_oauth.build_authorization_url(
            state=state, code_verifier=verifier, redirect_uri=_redirect_uri(request)
        ),
        status_code=303,
    )
    response.set_cookie(
        STATE_COOKIE_NAME,
        cookie_value,
        max_age=google_oauth.STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        # `lax`, not `strict`: Google's redirect back is a cross-site navigation, and
        # a strict cookie would not be sent with it — the flow would fail every time.
        samesite="lax",
        path="/",
    )
    return response


@router.get("/callback", name="google_callback")
async def google_callback(
    request: Request,
    db: DBSession,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    oauth_state: Annotated[str | None, Cookie(alias=STATE_COOKIE_NAME)] = None,
    strategy: DatabaseStrategy = Depends(get_database_strategy),
) -> Response:
    _require_enabled()

    # The person pressed "cancel" on Google's consent screen, or Google refused.
    if error or not code:
        return _error_redirect("cancelled" if error == "access_denied" else "no_code")

    try:
        verifier = google_oauth.read_state(oauth_state, state)
        access_token = await google_oauth.exchange_code(
            code=code, code_verifier=verifier, redirect_uri=_redirect_uri(request)
        )
        profile = await google_oauth.fetch_profile(access_token)

        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            # Nothing to join yet: the deployment has not been set up.
            return _error_redirect("not_initialized")

        repo = UserRepository(db)
        user = await google_oauth.resolve_account(store=repo, org=org, profile=profile)
        # A learner needs a profile row or the onboarding gate never fires — same
        # reasoning as `POST /users`. Idempotent, so a returning user is unaffected.
        if str(getattr(user.role, "value", user.role)) == "employee":
            await LearnerProfileRepository(db).get_or_create(
                user_id=user.id, org_id=org.id
            )
        await db.commit()
    except GoogleAuthError as exc:
        await db.rollback()
        logger.info("Google sign-in refused: %s", exc.reason)
        return _error_redirect(exc.reason)

    await db.refresh(user)
    login_response = await auth_backend.login(strategy, user)
    response = RedirectResponse(url=settings.GOOGLE_POST_LOGIN_PATH, status_code=303)
    # Carry the session cookie fastapi-users just minted onto the redirect. Going
    # through the backend rather than setting a cookie by hand keeps one definition
    # of what a SkillNet session is.
    for name, value in login_response.raw_headers:
        if name.lower() == b"set-cookie":
            response.raw_headers.append((name, value))
    response.delete_cookie(STATE_COOKIE_NAME, path="/")
    return response
