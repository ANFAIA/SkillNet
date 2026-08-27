"""Does a ``done`` artefact still have its file? — and what happens when it does not.

``media_artifacts`` records ``status='done'`` the moment a generator returns bytes, and the
asset store writes those bytes under ``MEDIA_ASSETS_DIR``. Those are two different
lifetimes: the row lives in Postgres, the file lives on a Docker volume. Lose the volume
(``compose down -v``, a renamed volume, bytes generated inside a container that no longer
exists) and every row keeps claiming ``done`` for ever, the asset route answers a bare
``404``, and the learner reads a red "Audio no disponible" for something no retry of theirs
can fix. Nothing anywhere records that the two disagree.

This module is the one place that reconciles them. Four decisions worth keeping:

* **The check rides the failure path, not the happy one.** Serving an asset already opens
  the file, so a ``FileNotFoundError`` *is* the check and a healthy request pays nothing
  extra. Only the single-row read spends one ``stat``, and no listing ever does — a course
  with fifty artefacts must not turn one query into fifty syscalls.
* **A ``done`` row with no file is demoted to ``error`` / ``asset_missing``.** Demotion is
  what stops the lie, and it does so for every reader at once: the studio shows a failure
  with its reason and its retry, ``MediaArtifactRead.asset_ref`` stops handing activities a
  ref to nothing, ``ActivityAssetResolver`` declines with ``asset_not_ready``, and the
  episode media broker stops offering the artefact to the generator. A row that stayed
  ``done`` would keep lying to all four.
* **Nothing is regenerated here.** Voicing a podcast or drawing a poster costs money; a
  *read* must never spend it. Demoting to ``error`` puts the artefact back on the normal,
  explicit "generate again" path and leaves the decision with a human.
* **``asset_path`` is kept, and the demotion is reversible.** The path is the only record of
  which file went missing, and the operator reading the log wants it. It is also what lets
  the demotion be undone: the asset store is content-addressed, so a file that reappears at
  that path *is* the original bytes by construction, and the row goes back to ``done``
  (:func:`restore_recovered_asset`). Restoring a volume from a backup therefore heals the
  rows too, instead of leaving them stuck in a failure that is no longer true.

The asset routes distinguish the two shapes of "no bytes", because they are not the same
incident: **nothing was ever generated** is a ``404`` (a spec-only artefact, or one still
running), while **it was generated and the file is gone** is a ``410`` with the
``asset_missing`` code — a deployment fault, logged at ``error``, that the client can word
for itself instead of guessing from a bare not-found.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError
from src.core.logging import get_logger
from src.models import MediaArtifact, MediaArtifactStatus
from src.services.media.jobs import ERROR_ASSET_MISSING, error_message

logger = get_logger(__name__)

#: How long a stored ``error`` may be. Mirrors ``jobs._ERROR_CHARS``; the sentences here
#: are far shorter, this only stops a future edit from writing an unbounded column.
_ERROR_CHARS = 500


class AssetMissingError(AppError):
    """The artefact was generated, but its bytes are no longer on this server.

    ``410 Gone`` rather than ``404``: the resource existed, the reference is valid, and it
    is not coming back without a new generation — which is exactly what ``410`` means and
    what a ``404`` cannot say. The distinction is the whole point of the status code here:
    a client seeing ``404`` cannot tell "this artefact never had an asset" from "this
    deployment lost its media volume", and neither can an operator reading an access log.

    ``code`` matches the row's ``error_code`` (``asset_missing``) so a client keys one
    message off one identifier whether it learns about the loss from the artefact row or
    from the failed asset request.
    """

    def __init__(self, artifact_id: str, *, ref: str | None = None) -> None:
        details: dict[str, str] = {"artifact_id": artifact_id}
        if ref is not None:
            details["ref"] = ref
        super().__init__(
            message=error_message(ERROR_ASSET_MISSING),
            code=ERROR_ASSET_MISSING,
            status_code=410,
            details=details,
        )


def _is_done(artifact: MediaArtifact) -> bool:
    status = getattr(artifact.status, "value", artifact.status)
    return str(status) == MediaArtifactStatus.DONE.value


def _already_recorded(artifact: MediaArtifact) -> bool:
    status = getattr(artifact.status, "value", artifact.status)
    return (
        str(status) == MediaArtifactStatus.ERROR.value
        and artifact.error_code == ERROR_ASSET_MISSING
    )


def asset_is_on_disk(artifact: MediaArtifact) -> bool:
    """Whether this artefact's main asset file exists right now.

    One ``stat``. Cheap per row and therefore fine on a single-artefact read — and
    deliberately not used by any listing, where it would multiply by the page size.
    """
    return bool(artifact.asset_path) and Path(artifact.asset_path).is_file()


async def record_missing_asset(
    db: AsyncSession, artifact: MediaArtifact, *, ref: str | None = None
) -> None:
    """Log the inconsistency and demote the row so it stops claiming to be ready.

    Best-effort by design: this is bookkeeping on top of a request that is failing anyway,
    so a database problem here is logged and swallowed rather than turned into a ``500``
    that hides the real cause.

    Logged at ``error`` because that is what it is — the deployment lost data it says it
    has — and logged only the first time, so a learner reloading the page does not print
    the same line fifty times. ``ref`` names the sub-asset when the loss was found through
    the per-slide route.
    """
    if _already_recorded(artifact):
        logger.debug(
            "Media artifact %s is already recorded as %s", artifact.id, ERROR_ASSET_MISSING
        )
        return

    logger.error(
        "Media artifact %s (%s) is '%s' but its %s is not on disk (%s). Demoting it to "
        "'error'/%s so it can be generated again. If this is every artefact at once, the "
        "media asset volume was lost, not one file.",
        artifact.id,
        getattr(artifact.kind, "value", artifact.kind),
        getattr(artifact.status, "value", artifact.status),
        f"sub-asset {ref}" if ref else "asset",
        artifact.asset_path,
        ERROR_ASSET_MISSING,
    )

    try:
        artifact.status = MediaArtifactStatus.ERROR
        artifact.error = error_message(ERROR_ASSET_MISSING)[:_ERROR_CHARS]
        artifact.error_code = ERROR_ASSET_MISSING
        await db.commit()
    except Exception:  # noqa: BLE001 - bookkeeping must not mask the response
        logger.error(
            "Could not demote media artifact %s after its asset went missing",
            artifact.id,
            exc_info=True,
        )
        await db.rollback()


async def restore_recovered_asset(
    db: AsyncSession, artifact: MediaArtifact, *, verified: bool = False
) -> bool:
    """Put a row demoted for a missing file back to ``done`` once the file is back.

    Only ever touches a row this module itself demoted (``error`` + ``asset_missing``), so
    a real generation failure is never resurrected. It is safe *because the store is
    content-addressed*: the file name is the sha256 of the bytes, so a file present at that
    path is the same asset the row was written for — there is nothing to re-validate.

    Without this, demotion would be a one-way door: an operator who restored the media
    volume from a backup would find every artefact a learner had happened to open in the
    meantime frozen in a failure that had stopped being true, and the only way out would be
    paying for a regeneration. ``verified`` says the caller has just read the file
    successfully, which saves the ``stat``.

    The proof is about the **main** asset only. An artefact that lives entirely in
    per-slide sub-assets (the Video Overview) has no single file to check, so one clip
    reading back does not prove the lost one did; such a row is left ``error`` and comes
    back through a regeneration, which is the honest answer rather than a guess.
    """
    if not _already_recorded(artifact):
        return False
    if not verified and not asset_is_on_disk(artifact):
        return False

    logger.info(
        "Media artifact %s has its asset back on disk (%s); restoring it to 'done'.",
        artifact.id,
        artifact.asset_path,
    )
    try:
        artifact.status = MediaArtifactStatus.DONE
        artifact.error = None
        artifact.error_code = None
        await db.commit()
    except Exception:  # noqa: BLE001 - bookkeeping must not mask the response
        logger.error(
            "Could not restore media artifact %s after its asset came back",
            artifact.id,
            exc_info=True,
        )
        await db.rollback()
        return False
    return True


async def reconcile_asset(db: AsyncSession, artifact: MediaArtifact) -> bool:
    """Make the row agree with the disk, in whichever direction they disagree.

    Returns whether the asset is servable. Three cases, one ``stat`` at most:

    * ``done`` with a file — nothing to do.
    * ``done`` with no file — demoted, logged (:func:`record_missing_asset`).
    * ``error``/``asset_missing`` with the file back — restored
      (:func:`restore_recovered_asset`).

    A ``pending``/``running`` row has nothing to be wrong about yet, and a spec-only
    artefact (``asset_path is None``) never promised bytes; both are left alone.

    This is the read path's half of the fix, for the one read where a ``stat`` is free:
    ``GET /media/artifacts/{id}``. It means the status the client polls is the status the
    asset route will honour a moment later, instead of the two disagreeing for ever.
    """
    if _already_recorded(artifact):
        return await restore_recovered_asset(db, artifact)
    if not _is_done(artifact) or not artifact.asset_path:
        return False
    if asset_is_on_disk(artifact):
        return True
    await record_missing_asset(db, artifact)
    return False


__all__ = [
    "AssetMissingError",
    "asset_is_on_disk",
    "record_missing_asset",
    "reconcile_asset",
    "restore_recovered_asset",
]
