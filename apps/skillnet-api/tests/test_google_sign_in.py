"""Sign in with Google: the matching rule, per workspace mode.

No DB and no network — the account store is a fake with the four methods the policy
actually calls, same pattern as ``test_account_self_service.py``. What is under test
is the decision, not the HTTP plumbing: which Google identities become a session,
which are refused, and which create an account.
"""

import uuid
from types import SimpleNamespace

import pytest

from src.models import UserRole, WorkspaceMode
from src.services.google_oauth import (
    GoogleAuthError,
    GoogleProfile,
    profile_from_claims,
    read_state,
    new_state,
    resolve_account,
)


class FakeStore:
    """The slice of ``UserRepository`` the policy uses."""

    def __init__(self, users: list | None = None) -> None:
        self.users = list(users or [])
        self.created: list[dict] = []
        self.updates: list[tuple] = []

    async def get_by_google_sub(self, google_sub):
        return next((u for u in self.users if getattr(u, "google_sub", None) == google_sub), None)

    async def get_by_email(self, org_id, email):
        return next(
            (u for u in self.users if u.org_id == org_id and u.email == email), None
        )

    async def create(self, **kwargs):
        self.created.append(dict(kwargs))
        user = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.users.append(user)
        return user

    async def update(self, obj, **kwargs):
        self.updates.append((obj, dict(kwargs)))
        for key, value in kwargs.items():
            setattr(obj, key, value)
        return obj


def make_org(mode=WorkspaceMode.ORGANIZATION):
    return SimpleNamespace(id=uuid.uuid4(), workspace_mode=mode)


def make_user(org, **overrides):
    base = dict(
        id=uuid.uuid4(),
        org_id=org.id,
        email="ada@acme.dev",
        full_name="Ada",
        role=UserRole.EMPLOYEE,
        is_active=True,
        google_sub=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_profile(**overrides):
    base = dict(
        sub="google-sub-1",
        email="ada@acme.dev",
        email_verified=True,
        full_name="Ada Lovelace",
    )
    base.update(overrides)
    return GoogleProfile(**base)


# ---------------------------------------------------------------------------
# Organization mode: match an invited person, never create one
# ---------------------------------------------------------------------------


async def test_org_mode_matches_an_existing_user_and_links_the_google_sub():
    org = make_org()
    ada = make_user(org)
    store = FakeStore([ada])

    resolved = await resolve_account(store=store, org=org, profile=make_profile())

    assert resolved is ada
    assert ada.google_sub == "google-sub-1"
    assert store.created == [], "org mode must never create an account"


async def test_org_mode_refuses_an_email_nobody_invited():
    org = make_org()
    store = FakeStore([make_user(org, email="someone.else@acme.dev")])

    with pytest.raises(GoogleAuthError) as exc:
        await resolve_account(store=store, org=org, profile=make_profile())

    assert exc.value.reason == "not_invited"
    assert exc.value.status_code == 403
    assert store.created == []


async def test_a_second_sign_in_matches_on_the_sub_not_the_email():
    """The person changed their Google address; it is still the same account."""
    org = make_org()
    ada = make_user(org, google_sub="google-sub-1")
    store = FakeStore([ada])

    resolved = await resolve_account(
        store=store, org=org, profile=make_profile(email="ada.new@acme.dev")
    )

    assert resolved is ada
    assert store.updates == [], "already linked — nothing to write"


async def test_an_account_already_linked_to_a_different_google_identity_is_refused():
    org = make_org()
    store = FakeStore([make_user(org, google_sub="somebody-elses-sub")])

    with pytest.raises(GoogleAuthError) as exc:
        await resolve_account(store=store, org=org, profile=make_profile())

    assert exc.value.reason == "already_linked"


async def test_a_deactivated_account_cannot_sign_in_with_google():
    org = make_org()
    store = FakeStore([make_user(org, is_active=False)])

    with pytest.raises(GoogleAuthError) as exc:
        await resolve_account(store=store, org=org, profile=make_profile())

    assert exc.value.reason == "inactive"


# ---------------------------------------------------------------------------
# The verified-email requirement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [WorkspaceMode.ORGANIZATION, WorkspaceMode.INDIVIDUAL])
async def test_an_unverified_email_never_matches_anything(mode):
    """Refused before any lookup: an unverified address is attacker-controlled."""
    org = make_org(mode)
    ada = make_user(org)
    store = FakeStore([ada])

    with pytest.raises(GoogleAuthError) as exc:
        await resolve_account(
            store=store, org=org, profile=make_profile(email_verified=False)
        )

    assert exc.value.reason == "email_unverified"
    assert store.created == []
    assert store.updates == []
    assert ada.google_sub is None


def test_a_missing_email_verified_claim_counts_as_unverified():
    profile = profile_from_claims({"sub": "s", "email": "Ada@Acme.dev", "name": "Ada"})
    assert profile.email_verified is False
    # And the address is normalized, so matching is not case-sensitive.
    assert profile.email == "ada@acme.dev"


def test_a_string_true_is_not_a_verified_email():
    """Only a real boolean counts; `"false"` is truthy in Python and must not pass."""
    claims = {"sub": "s", "email": "a@b.dev", "email_verified": "false"}
    assert profile_from_claims(claims).email_verified is False


# ---------------------------------------------------------------------------
# Individual mode: self-registration
# ---------------------------------------------------------------------------


async def test_individual_mode_creates_the_account():
    org = make_org(WorkspaceMode.INDIVIDUAL)
    store = FakeStore()

    resolved = await resolve_account(store=store, org=org, profile=make_profile())

    assert len(store.created) == 1
    created = store.created[0]
    assert created["org_id"] == org.id
    assert created["email"] == "ada@acme.dev"
    assert created["google_sub"] == "google-sub-1"
    assert created["role"] is UserRole.EMPLOYEE
    assert created["is_active"] is True
    # No usable password: this account signs in through Google only.
    assert created["hashed_password"] == ""
    assert resolved.email == "ada@acme.dev"


async def test_individual_mode_still_refuses_an_unverified_email():
    org = make_org(WorkspaceMode.INDIVIDUAL)
    store = FakeStore()

    with pytest.raises(GoogleAuthError):
        await resolve_account(
            store=store, org=org, profile=make_profile(email_verified=False)
        )
    assert store.created == []


async def test_individual_mode_links_the_owner_rather_than_creating_a_second_account():
    org = make_org(WorkspaceMode.INDIVIDUAL)
    owner = make_user(org, role=UserRole.ADMIN)
    store = FakeStore([owner])

    resolved = await resolve_account(store=store, org=org, profile=make_profile())

    assert resolved is owner
    assert owner.role is UserRole.ADMIN, "linking must not change the role"
    assert store.created == []


# ---------------------------------------------------------------------------
# CSRF state + PKCE cookie
# ---------------------------------------------------------------------------


def test_the_state_cookie_round_trips_and_returns_the_pkce_verifier():
    state, verifier, cookie = new_state()
    assert read_state(cookie, state) == verifier


def test_a_state_that_does_not_match_the_cookie_is_refused():
    _, _, cookie = new_state()
    with pytest.raises(GoogleAuthError) as exc:
        read_state(cookie, "state-from-somewhere-else")
    assert exc.value.reason == "invalid_state"


def test_a_tampered_state_cookie_is_refused():
    state, _, cookie = new_state()
    payload, signature = cookie.rsplit(".", 1)
    with pytest.raises(GoogleAuthError):
        read_state(f"{payload}x.{signature}", state)


def test_a_missing_state_cookie_is_refused():
    with pytest.raises(GoogleAuthError):
        read_state(None, "anything")
