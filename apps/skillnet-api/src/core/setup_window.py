"""How long `POST /setup` stays open, and how to reopen it once it has closed.

`POST /setup` has to be public: it is how the very first owner account gets created, so
there is nobody to authenticate as yet. It closes for good once an owner exists. The gap
between those two facts is the problem — while a deployment has no owner, whoever reaches
it first becomes its owner.

That gap is harmless on localhost and dangerous the moment the instance is reachable from
the internet, which is easy to do by accident: bring the stack up, start a tunnel, then go
and create the account. "Nobody knows the address yet" is not true either — a
trycloudflare hostname is guessable, and a Caddy certificate is published to Certificate
Transparency logs the second it is issued.

So the window is time-boxed. It opens when the API starts with no owner and closes after
``SETUP_WINDOW_MINUTES``. An operator installing the thing needs a couple of minutes; an
attacker scanning for fresh deployments needs to arrive inside the same few minutes as the
person doing the install.

Closing it outright would lock out anyone who was slow, so there is one way back in: a
token generated at startup and written to the API log. Recovering it requires access to
``docker compose logs api``, which is the same access that could read the database anyway.
That keeps the browser wizard working with nothing to copy in the normal case, and leaves
a recovery path that a random visitor cannot use.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SetupWindow:
    """Process-local state. Restarting the API opens a fresh window, on purpose.

    Not persisted anywhere: a restart is the documented way to get another window, and it
    is an action that already requires host access.
    """

    opened_at: float | None = None
    token: str | None = None

    def open(self, minutes: int) -> None:
        self.opened_at = time.monotonic()
        self.token = secrets.token_urlsafe(24)
        if minutes <= 0:
            logger.warning(
                "Setup window is open with NO time limit (SETUP_WINDOW_MINUTES=%s). "
                "Anyone who can reach this instance can claim ownership of it.",
                minutes,
            )
            return
        # At warning level and framed as an instruction: on a normal boot this is the one
        # line in the log the operator actually needs.
        logger.warning(
            "No owner account yet. Open the app and complete /setup within %d minutes. "
            "After that, reopen the window by restarting this container, or pass this "
            "token as the X-Setup-Token header: %s",
            minutes,
            self.token,
        )

    def is_open(self, minutes: int) -> bool:
        if self.opened_at is None:
            return False
        if minutes <= 0:
            return True
        return (time.monotonic() - self.opened_at) < minutes * 60

    def token_matches(self, candidate: str | None) -> bool:
        """Constant-time compare, and never true for an absent token on either side."""
        if not candidate or not self.token:
            return False
        return secrets.compare_digest(candidate, self.token)


#: One per process, populated by the app lifespan.
window = SetupWindow()
