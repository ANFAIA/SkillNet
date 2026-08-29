"""Onboarding schemas — and the onboarding **copy**, which lives here on purpose.

The server ships the questions (§11.2) so the wording exists in exactly one
place: a wizard that hardcodes its own labels drifts from the fields it writes,
and the RGPD art. 13 notice in particular must not be optional client copy.
That is why :data:`PRIVACY_NOTICE` is a field of ``OnboardingRead`` and not a
string in a React component (§3.3).

One question per screen, ≤3 visible elements, target ≤90 s (§6.1). §6.2 tables
five screens; the declared-modality screen (``learning_preferences``) was added
on top of them, so there are **six**, and the last two are both optional — a
learner who skips them costs four screens, which is what the ≤90 s budget of
§6.1 actually needs. Count them from :func:`build_questions`, never from the
prose: the client mirrors this list and the flow test pins it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Single definition, owned by the service that writes
# ``learner_profiles.onboarding_version``. Re-exported here so callers can import
# the version next to the questions it describes.
from src.schemas.learning_preferences import (
    AccessibilitySubmit,
    LearningPreferencesSubmit,
)
from src.services.learner_profile_service import ONBOARDING_VERSION

__all__ = [
    "ACCESSIBILITY_KEYS",
    "ONBOARDING_VERSION",
    "PRIVACY_NOTICE",
    "ROLE_SUGGESTIONS",
    "AccessibilitySubmit",
    "OnboardingOption",
    "OnboardingQuestion",
    "OnboardingRead",
    "OnboardingSubmit",
    "build_questions",
    "role_suggestions",
]

#: RGPD art. 13 notice, shown on screen 1 with the same visual weight as the
#: question. Requirement, not copy suggestion (§3.3).
PRIVACY_NOTICE = (
    "Tu puesto y tu sector se envían al proveedor de IA para adaptar los "
    "ejemplos. Puedes borrarlos cuando quieras desde Ajustes."
)

#: Six role suggestions per sector for question 1 (§6.2). The sector comes from
#: ``organizations.settings["sector"]``; anything unknown falls back to
#: ``"default"``. Suggestions only — question 1 stays free text.
ROLE_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "default": (
        "Técnico",
        "Administrativo",
        "Comercial",
        "Encargado de turno",
        "Responsable de equipo",
        "Operario",
    ),
    "retail": (
        "Dependiente",
        "Cajero",
        "Encargado de turno",
        "Reponedor",
        "Responsable de tienda",
        "Atención al cliente",
    ),
    "hosteleria": (
        "Camarero",
        "Cocinero",
        "Ayudante de cocina",
        "Recepcionista",
        "Encargado de sala",
        "Barman",
    ),
    "logistica": (
        "Mozo de almacén",
        "Carretillero",
        "Repartidor",
        "Preparador de pedidos",
        "Jefe de almacén",
        "Administrativo de tráfico",
    ),
    "sanidad": (
        "Auxiliar de enfermería",
        "Enfermero",
        "Recepcionista",
        "Técnico de laboratorio",
        "Celador",
        "Coordinador de planta",
    ),
    "construccion": (
        "Oficial de primera",
        "Peón",
        "Encargado de obra",
        "Electricista",
        "Fontanero",
        "Jefe de equipo",
    ),
    "oficina": (
        "Administrativo",
        "Contable",
        "Comercial",
        "Recursos humanos",
        "Soporte informático",
        "Responsable de equipo",
    ),
}

#: The four functional reading settings (``users.accessibility``). Declared audio
#: modality is stored separately in ``learning_preferences``.
ACCESSIBILITY_KEYS: tuple[str, ...] = (
    "short_blocks",
    "reduce_motion",
    "high_contrast",
    "extra_time",
)

QuestionKind = Literal["text_suggest", "single_choice", "multi_choice"]


class OnboardingOption(BaseModel):
    value: str
    label: str
    hint: str | None = None


class OnboardingQuestion(BaseModel):
    """One screen. Absent keys are omitted from the JSON (``exclude_none``)."""

    id: str
    kind: QuestionKind
    prompt: str
    suggestions: list[str] | None = None
    options: list[OnboardingOption] | None = None
    allow_other: bool | None = None
    optional: bool | None = None


class OnboardingRead(BaseModel):
    version: int = ONBOARDING_VERSION
    completed: bool = False
    notice: str = PRIVACY_NOTICE
    audio_available: bool = False
    questions: list[OnboardingQuestion] = []


class OnboardingSubmit(BaseModel):
    """``POST /onboarding``.

    Every field is optional: the wizard is skippable at any point and a
    partially-answered submission must still land. An absent
    ``experience_level`` becomes ``unknown``, never ``none`` (§6.1) — that
    mapping lives in the service, not here, so ``skip`` and a partial submit
    cannot diverge.
    """

    model_config = ConfigDict(extra="forbid")

    role_title: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    goal: str | None = Field(default=None, max_length=200)
    experience_level: Literal["none", "some", "experienced"] | None = None
    preset: Literal["standard", "focus", "fast"] | None = None
    accessibility: AccessibilitySubmit | None = None
    learning_preferences: LearningPreferencesSubmit | None = None


def role_suggestions(sector: str | None) -> list[str]:
    """Six suggestions for the org's sector, falling back to the generic list."""
    key = (sector or "").strip().lower()
    return list(ROLE_SUGGESTIONS.get(key, ROLE_SUGGESTIONS["default"]))


def build_questions(
    *, sector: str | None = None, audio_available: bool = False
) -> list[OnboardingQuestion]:
    """The six questions, in order: the five of §6.2 plus declared modality.

    The order is part of the contract — the wizard renders the list as it
    arrives and dispatches on ``id`` — and ``learning_preferences`` goes
    **before** ``accessibility`` on purpose: one asks how the learner wants to
    be taught, the other what they need in order to read at all, and the
    functional-needs screen is the last one of §6.2.

    What is **not** asked is as deliberate as what is (§6.3): no initial level
    test (the per-node pre-assessment does it better, per competence), no
    fixed learning-style label (declared modality is only a reversible priority)
    and no neurodivergence diagnosis (art. 9 special-category data — the
    ``accessibility`` question asks about needs, not conditions).
    """
    return [
        OnboardingQuestion(
            id="role_title",
            kind="text_suggest",
            prompt="¿Cuál es tu puesto?",
            suggestions=role_suggestions(sector),
        ),
        OnboardingQuestion(
            id="goal",
            kind="single_choice",
            prompt="¿Para qué quieres usar SkillNet ahora mismo?",
            options=[
                OnboardingOption(
                    value="onboarding",
                    label="Acabo de entrar y quiero ponerme al día",
                ),
                OnboardingOption(
                    value="specific_gap",
                    label="Hay algo concreto que necesito dominar",
                ),
                OnboardingOption(value="assigned", label="Me han asignado formación"),
            ],
            allow_other=True,
        ),
        OnboardingQuestion(
            id="experience_level",
            kind="single_choice",
            prompt="¿Cuánta experiencia tienes en tu puesto actual?",
            options=[
                OnboardingOption(value="none", label="Ninguna"),
                OnboardingOption(value="some", label="Algo"),
                OnboardingOption(value="experienced", label="Bastante"),
            ],
        ),
        OnboardingQuestion(
            id="preset",
            kind="single_choice",
            prompt="¿Cómo prefieres estudiar?",
            options=[
                OnboardingOption(
                    value="standard", label="Estándar", hint="Bloques de 10-15 min"
                ),
                OnboardingOption(
                    value="focus",
                    label="Concentración",
                    hint="Paso a paso, sin distracciones",
                ),
                OnboardingOption(
                    value="fast", label="Ritmo rápido", hint="Micro-bloques de 3-5 min"
                ),
            ],
        ),
        OnboardingQuestion(
            id="learning_preferences",
            kind="single_choice",
            prompt="¿Cómo te gustaría aprender normalmente?",
            optional=True,
            options=[
                OnboardingOption(
                    value="balanced",
                    label="Equilibrado",
                    hint="SkillNet mezcla formatos según el contenido",
                ),
                OnboardingOption(
                    value="visual",
                    label="Más visual",
                    hint="Prioriza diagramas, tablas e imágenes útiles",
                ),
                OnboardingOption(
                    value="text",
                    label="Más texto",
                    hint="Prioriza explicaciones estructuradas",
                ),
                OnboardingOption(
                    value="audio",
                    label="Audio",
                    hint=(
                        "Prioriza explicaciones escuchadas"
                        if audio_available
                        else "Depende del proveedor configurado en este despliegue"
                    ),
                ),
                OnboardingOption(
                    value="data",
                    label="Datos",
                    hint="Prioriza tablas, cifras y comparaciones",
                ),
            ],
        ),
        OnboardingQuestion(
            id="accessibility",
            kind="multi_choice",
            prompt="¿Quieres activar algún ajuste de lectura?",
            optional=True,
            options=[
                OnboardingOption(value="short_blocks", label="Bloques más cortos"),
                OnboardingOption(value="reduce_motion", label="Menos animaciones"),
                OnboardingOption(value="high_contrast", label="Más contraste"),
                OnboardingOption(value="extra_time", label="Sin límite de tiempo"),
            ],
        ),
    ]
