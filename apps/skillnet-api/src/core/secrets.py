"""Encryption at rest for the provider credentials an organization stores.

``organizations.settings`` is a JSONB column, and an admin who configures their own LLM
provider puts an API key in it. The API has never returned that key — ``GET /settings``
reports ``llm_configured`` and the model name and nothing else — but until now it sat in
Postgres in clear text, readable by anyone with a psql prompt, a backup file or a replica.
For a tool other companies are meant to run with *their* keys, that is not good enough.

The shape of the solution, and its limits, stated plainly:

* **Fernet (AES-128-CBC + HMAC), keyed off ``SECRET_KEY``.** No new secret to manage: the
  deployment already must set ``SECRET_KEY`` and already must keep it safe, because it
  signs sessions. Adding a second secret nobody rotates would be theatre.
* **This protects the database, not the process.** A running API must be able to call the
  provider, so it must be able to decrypt. Anyone who can read process memory or the
  environment can get the key regardless. What this stops is the far more likely leak: a
  dump, a backup, a support query, a snapshot handed to a contractor.
* **Rotating ``SECRET_KEY`` makes stored keys unreadable.** That is inherent, and it is
  handled as a degradation rather than an outage — see :func:`unseal`.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

#: Marks a value this module produced. Anything without it is read as legacy clear text,
#: which is what makes deploying this a no-op for installations that already stored a key:
#: they keep working, and the value is sealed the next time it is written.
PREFIX = "enc:v1:"

#: Domain separation. ``SECRET_KEY`` also signs session cookies; deriving rather than
#: using it directly means the two uses cannot be played against each other.
_SALT = b"skillnet.org-settings.v1"


def _fernet() -> Fernet:
    digest = hashlib.pbkdf2_hmac(
        "sha256", settings.SECRET_KEY.encode("utf-8"), _SALT, 100_000, dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(digest))


def is_sealed(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def seal(plaintext: str | None) -> str | None:
    """Encrypt a credential for storage. ``None`` and empty pass through unchanged.

    Idempotent: sealing an already-sealed value returns it as it is, so a settings update
    that carries the stored value back in does not double-encrypt it.
    """
    if not plaintext:
        return plaintext
    if is_sealed(plaintext):
        return plaintext
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def unseal(stored: str | None) -> str | None:
    """Read a credential back.

    Three cases, and all three are ordinary:

    * sealed by this module -> decrypted;
    * clear text from before this existed -> returned as it is, so nothing breaks the day
      this ships;
    * sealed but undecryptable -> ``None`` with a warning.

    That last one is what happens when ``SECRET_KEY`` is rotated or a database is copied
    between deployments. Returning ``None`` degrades to "this organization has no key
    configured", so the environment default takes over and the admin sees the provider
    reported as unconfigured — which is the truth. Raising instead would take down every
    request that touches an LLM, for a condition an admin fixes by re-entering the key.
    """
    if not stored:
        return None
    text = str(stored)
    if not is_sealed(text):
        return text
    try:
        return _fernet().decrypt(text[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.warning(
            "A stored provider credential could not be decrypted; treating the "
            "organization as having none. This is what a rotated SECRET_KEY looks "
            "like — the admin needs to re-enter the key in Ajustes."
        )
        return None


__all__ = ["PREFIX", "is_sealed", "seal", "unseal"]
