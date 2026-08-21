"""Keyless, per-org pre-baked demo course for admin onboarding.

A brand-new organization gets exactly one tiny course so the onboarding tour has real
content to walk through on the real screens (Contenido, the admin ``probar-curso``
NodeView). Unlike ``seed_learning_demo``, this runs **no LLM**: the rows are inserted
directly and the showcase node ships two pre-validated ``NodeRender`` variants so the
admin can flip between learner preferences instantly, without any generation.

The showcase node carries TWO pre-baked renders — an audio/metaphor-leaning one and a
visual/definitions-leaning one — one per preference bucket. They are ``is_preview`` rows
so they never enter the shared render cache (``NodeRenderRepository.find_cached`` filters
``is_preview`` out), and they are keyed by a deterministic ``demo-preview:{bucket}:{node}``
cache key that ``GET /nodes/{id}/render?preview_pref=…`` looks up directly and serves as a
cache hit. A real learner opening the demo course still goes through the normal render
path; this module only guarantees the admin's tour never has to generate anything.

The course is served as a normal **dynamic (v2)** course — ``delivery_mode='dynamic'`` +
``schema_status='validated'`` — because that is the single condition
``course_delivery.resolve_delivery`` checks, and it is what makes the ``/nodes`` surface
(and the NodeView the tour visits) treat the course as existing. Its nodes carry
``reviewed_at`` so ``NodeRenderService.assert_reviewed`` lets them be served.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models import (
    Course,
    CourseNode,
    NodeRender,
    NodeRenderStatus,
    Organization,
)
from src.models.course import (
    ContentStatus,
    CourseDeliveryMode,
    CourseSchemaStatus,
)
from src.models.course_node import NodeCriticality
from src.models.node_render import UiFormat
from src.render.backends.openui import OpenUiLangBackend
from src.render.prompt import catalog_version, library_version
from src.render.spec import UISpec

logger = get_logger(__name__)

#: Marker so the demo course is trivially found (idempotency) and greppable.
DEMO_COURSE_TITLE = "Cómo aprende tu cerebro (demo)"

#: The two preference buckets the showcase node is pre-baked for. ``audio`` leans on a
#: metaphor plus a spoken explanation; ``visual`` leans on definitions, a chart and a
#: table.
PREVIEW_BUCKETS: tuple[str, ...] = ("audio", "visual")

#: Prefix of the deterministic cache key of a pre-baked preview render. It never collides
#: with a real ``cache_key`` (those are salted/prefixed differently) and is what the
#: ``preview_pref`` query param resolves against.
DEMO_PREVIEW_KEY_PREFIX = "demo-preview"


def demo_preview_cache_key(node_id: uuid.UUID, bucket: str) -> str:
    """The deterministic key under which the ``bucket`` variant of ``node_id`` is stored."""
    return f"{DEMO_PREVIEW_KEY_PREFIX}:{bucket}:{node_id}"


# --------------------------------------------------------------------------------------
# The pre-baked programs, written in the OpenUI dialect (referenced form). They are parsed
# and validated through the real backend at seed time, so a program that stops satisfying
# the §5.2 contract fails loudly here instead of shipping a broken screen.
# --------------------------------------------------------------------------------------

AUDIO_PROGRAM = (
    'lead = TextContent("Tu memoria es un jardinero nocturno: mientras duermes, poda lo '
    'que sobra y riega lo que de verdad importa.", "lead")\n'
    'analogia = Callout("info", "Igual que el jardinero no planta de día, tu cerebro fija '
    'lo aprendido sobre todo al dormir. Un repaso corto antes de acostarte le deja las '
    'semillas listas para crecer.")\n'
    'audio = AudioExplanation("En una frase: dormir es el momento en que tu memoria decide '
    'qué se queda y qué se olvida.", "warm")\n'
    'root = Stack([lead, analogia, audio], "md")\n'
)

VISUAL_PROGRAM = (
    'lead = TextContent("Consolidación: proceso por el que un recuerdo lábil pasa a un '
    'almacenamiento estable, dependiente del sueño y de la repetición espaciada.", "lead")\n'
    'curva = Chart("bar", "Cuánto se retiene sin repaso (curva del olvido)", '
    '["20 min", "1 día", "6 días"], [58, 34, 21])\n'
    'pasos = StepSequence("El ciclo de la memoria", '
    '["Codificación: la información entra y se representa en el hipocampo.", '
    '"Consolidación: durante el sueño pasa a la corteza y se estabiliza.", '
    '"Recuperación: reactivar el rastro lo refuerza mediante repaso espaciado."])\n'
    'terminos = Table(["Término", "Definición"], '
    '[["Lábil", "Recuerdo aún frágil, fácil de perder."], '
    '["Repaso espaciado", "Repetir con intervalos crecientes para fijarlo."]])\n'
    'root = Stack([lead, curva, pasos, terminos], "md")\n'
)

#: ``bucket -> (dialect program, declared UI format)``.
_SHOWCASE_PROGRAMS: dict[str, tuple[str, str]] = {
    "audio": (AUDIO_PROGRAM, UiFormat.EXPLANATION.value),
    "visual": (VISUAL_PROGRAM, UiFormat.CHART.value),
}


def build_showcase_specs() -> dict[str, tuple[UISpec, str]]:
    """Parse and validate the two pre-baked programs. ``bucket -> (spec, ui_format)``.

    Raises ``RenderError``/``RenderParseError`` if a program stops validating, which is
    exactly what the unit test asserts does not happen.
    """
    backend = OpenUiLangBackend()
    specs: dict[str, tuple[UISpec, str]] = {}
    for bucket, (program, ui_format) in _SHOWCASE_PROGRAMS.items():
        spec = backend.parse(program, ui_format=ui_format)
        specs[bucket] = (spec, ui_format)
    return specs


# --------------------------------------------------------------------------------------
# The node outline. Only the first node is a rich showcase; the other two exist so the
# node list and progression have something to show.
# --------------------------------------------------------------------------------------

_NODES: tuple[dict[str, str], ...] = (
    {
        "title": "Cómo se fija un recuerdo",
        "summary": "Por qué el sueño y el repaso deciden qué aprendes de verdad.",
        "outcome": "Explicar en una frase qué hace la consolidación de la memoria.",
    },
    {
        "title": "La curva del olvido",
        "summary": "Cuánto se pierde sin repaso, y cuándo conviene repasar.",
        "outcome": "Situar un repaso en el momento en que rinde más.",
    },
    {
        "title": "Repaso espaciado en la práctica",
        "summary": "Convertir la teoría en una rutina de repasos con intervalos crecientes.",
        "outcome": "Diseñar un plan de repaso simple para un tema propio.",
    },
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _existing_demo_course(session: AsyncSession, org_id: uuid.UUID) -> Course | None:
    result = await session.execute(
        select(Course).where(Course.org_id == org_id, Course.is_demo.is_(True)).limit(1)
    )
    return result.scalar_one_or_none()


async def seed_org_demo(session: AsyncSession, org: Organization) -> Course | None:
    """Idempotently insert the pre-baked demo course for ``org``.

    Running twice yields exactly one demo course: the second call finds the first and
    returns it untouched. Adds rows to ``session`` and flushes; the caller owns the
    commit. No LLM, no generation, no network.
    """
    existing = await _existing_demo_course(session, org.id)
    if existing is not None:
        return existing

    # Validate the pre-baked programs up front, before any row is written.
    specs = build_showcase_specs()
    catalog = catalog_version()
    library = library_version()

    course = Course(
        org_id=org.id,
        title=DEMO_COURSE_TITLE,
        description=(
            "Un mini-curso de demostración sobre cómo aprende la mente. Sirve para "
            "recorrer las pantallas reales durante el onboarding."
        ),
        outcome="Recorrer una lección real y sus componentes interactivos.",
        status=ContentStatus.PUBLISHED,
        delivery_mode=CourseDeliveryMode.DYNAMIC,
        schema_status=CourseSchemaStatus.VALIDATED,
        schema_validated_at=_now(),
        schema_version=1,
        intent_density=3,
        is_demo=True,
    )
    session.add(course)
    await session.flush()

    nodes: list[CourseNode] = []
    for position, spec in enumerate(_NODES):
        node = CourseNode(
            org_id=org.id,
            course_id=course.id,
            title=spec["title"],
            summary=spec["summary"],
            outcome=spec["outcome"],
            criticality=NodeCriticality.RECOMMENDED,
            position=position,
            default_ui_format=UiFormat.EXPLANATION,
            estimated_minutes=3,
            reviewed_at=_now(),
        )
        session.add(node)
        nodes.append(node)
    await session.flush()

    # Only the first (showcase) node gets the two pre-baked variants.
    showcase = nodes[0]
    backend = OpenUiLangBackend()
    for bucket in PREVIEW_BUCKETS:
        ui_spec, ui_format = specs[bucket]
        session.add(
            NodeRender(
                org_id=org.id,
                node_id=showcase.id,
                cache_key=demo_preview_cache_key(showcase.id, bucket),
                ui_format=UiFormat(ui_format),
                ui_spec=ui_spec.model_dump(mode="json"),
                answer_key={},
                dialect=backend.serialize(ui_spec),
                catalog_version=catalog,
                library_version=library,
                backend=backend.name,
                model="prebaked/demo",
                tier="fast",
                status=NodeRenderStatus.READY,
                # Kept out of the shared cache: a pre-baked preview must never be served to
                # a real learner as if it were their personalized render.
                is_preview=True,
            )
        )
    await session.flush()

    logger.info(
        "Seeded pre-baked demo course %s for org %s (%s nodes, %s showcase variants)",
        course.id,
        org.id,
        len(nodes),
        len(PREVIEW_BUCKETS),
    )
    return course


__all__ = [
    "AUDIO_PROGRAM",
    "DEMO_COURSE_TITLE",
    "DEMO_PREVIEW_KEY_PREFIX",
    "PREVIEW_BUCKETS",
    "VISUAL_PROGRAM",
    "build_showcase_specs",
    "demo_preview_cache_key",
    "seed_org_demo",
]
