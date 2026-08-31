"""The content-creation path in a second language, and the default path untouched.

Two things can break here and they pull in opposite directions.

The first is the feature: a course created from a title in English used to come out in
Spanish, because the source document — the only thing every later stage has to imitate
— was written by a prompt with "En espanol claro y directo" in its body. So the tests
below follow the language from the request into the system prompt of the call that
writes that document, and from the course row into the schema designer.

The second is everything that already worked. ``FixtureLLMService`` keys recorded
answers on ``sha256(system + "\\x00" + user)``, so one extra character in a prompt on
the default path silently invalidates every recording, the offline tests and
``scripts/quality_bench.py --offline``. The pinned keys in the first test are there to
fail loudly instead: if one of them changes, a prompt on the default path was edited and
the fixtures have to be re-recorded — which is a decision, not a detail.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.language import DEFAULT_LANGUAGE, accept_language, normalize_language
from src.knowledge_pack.configured_generator import ConfiguredKnowledgePackGenerator
from src.knowledge_pack.node_source import seed_node_source
from src.llm.client import Usage
from src.llm.fixtures import FixtureLLMService
from src.llm.prompts.generation import (
    CONTENT_REFINER_SYSTEM,
    MODULE_GENERATOR_SYSTEM,
    QUALITY_REVIEWER_SYSTEM,
    STRUCTURE_DESIGNER_SYSTEM,
    THEME_EXTRACTOR_SYSTEM,
)
from src.llm.prompts.language import with_language
from src.llm.prompts.probe import PROBE_GENERATOR_SYSTEM, build_probe_prompt
from src.llm.prompts.schema import SCHEMA_DESIGNER_SYSTEM, build_schema_prompt
from src.llm.prompts.source import (
    NODE_SOURCE_WRITER_SYSTEM,
    SOURCE_WRITER_SYSTEM,
    build_node_source_prompt,
    build_source_prompt,
)
from src.services.language_policy import ambient_language, language_for_course
from src.services.document_service import DocumentService

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

#: Long enough to pass ``_MIN_SOURCE_CHARS``; the content is irrelevant here.
GOOD_SOURCE = "## Una seccion\n\n" + "Contenido util del documento. " * 40

#: Every system prompt on the content-creation path, by the name of the agent that
#: sends it. Named rather than listed so a failure says which prompt broke.
CREATION_PROMPTS = {
    "source_writer": SOURCE_WRITER_SYSTEM,
    "node_source_writer": NODE_SOURCE_WRITER_SYSTEM,
    "theme_extractor": THEME_EXTRACTOR_SYSTEM,
    "structure_designer": STRUCTURE_DESIGNER_SYSTEM,
    "module_generator": MODULE_GENERATOR_SYSTEM,
    "quality_reviewer": QUALITY_REVIEWER_SYSTEM,
    "content_refiner": CONTENT_REFINER_SYSTEM,
    "schema_designer": SCHEMA_DESIGNER_SYSTEM,
    "probe_generator": PROBE_GENERATOR_SYSTEM,
}


# --------------------------------------------------------------------------------------
# The default path is byte for byte what it was
# --------------------------------------------------------------------------------------
def test_the_two_source_writer_prompts_still_hash_to_the_same_fixture_keys():
    """The pinned keys of the prompts nobody may edit.

    These two write the source document, they are the only prompts in the product with
    Spanish hardcoded in the body, and they are therefore the two most tempting to
    "fix". A failure here means a system prompt or a user-prompt builder on the default
    path changed, so every recorded fixture keyed on it is now unreachable — including
    the ones the offline quality bench replays. Re-recording is a deliberate act; this
    test exists so it cannot happen by accident.
    """
    course_key = FixtureLLMService.key_for(
        SOURCE_WRITER_SYSTEM,
        build_source_prompt(title="Alergenos alimentarios", idea="los 14 obligatorios"),
    )
    node_key = FixtureLLMService.key_for(
        NODE_SOURCE_WRITER_SYSTEM,
        build_node_source_prompt(
            course_title="Alergenos alimentarios",
            course_idea="los 14 obligatorios",
            node_title="Contaminacion cruzada",
            summary="Separar utensilios por alergeno.",
            outcome="Evitar el contacto entre alimentos.",
        ),
    )

    assert course_key == "786b70542937d68b"
    assert node_key == "565667222cfa5cd0"


@pytest.mark.parametrize("name", sorted(CREATION_PROMPTS))
def test_no_language_returns_the_very_same_object(name: str):
    """``is``, not ``==``: no rstrip, no re-wrap, nothing that could shift a byte."""
    prompt = CREATION_PROMPTS[name]
    assert with_language(prompt, None) is prompt


def test_no_language_leaves_every_user_prompt_builder_identical():
    """Passing ``language=None`` has to equal not passing it at all.

    The fixture key hashes the user prompt as well as the system one, so a builder that
    grew a language line would break the recordings from the other side.
    """
    assert build_source_prompt(title="T", idea="I") == build_source_prompt(
        title="T", idea="I", language=None
    )
    node_args = dict(
        course_title="C",
        course_idea="I",
        node_title="N",
        summary="S",
        outcome="O",
    )
    assert build_node_source_prompt(**node_args) == build_node_source_prompt(
        **node_args, language=None
    )
    assert build_schema_prompt([], {}, ["Uno"]) == build_schema_prompt(
        [], {}, ["Uno"], language=None
    )
    assert build_probe_prompt(title="N", summary="S") == build_probe_prompt(
        title="N", summary="S", language=None
    )


# --------------------------------------------------------------------------------------
# Asking for a language
# --------------------------------------------------------------------------------------
def test_a_locale_tag_is_accepted_where_a_language_is_expected():
    """What a browser sends, not what the type says: ``en-US``, ``es_ES``, ``EN``."""
    assert normalize_language("en-US") == "en"
    assert normalize_language("es_ES") == "es"
    assert normalize_language("EN") == "en"
    assert normalize_language("de-DE") is None
    assert normalize_language(None) is None
    # And the header form, which is the one the from-idea route falls back to.
    assert accept_language("en-GB,en;q=0.9,es;q=0.4") == "en"


def test_the_from_idea_request_takes_a_locale_and_not_only_a_language():
    """``POST /documents/from-idea`` is where a browser's value arrives first.

    A 422 naming the two supported values would be technically correct and useless:
    the client sent ``en-US`` because that is what it has. An unsupported locale is
    dropped rather than rejected, so a client cannot fail a request by preferring
    German; it just does not get German.
    """
    from src.routes.documents import SourceFromIdeaRequest

    assert SourceFromIdeaRequest(title="t", language="en-US").language == "en"
    assert SourceFromIdeaRequest(title="t", language="es_ES").language == "es"
    assert SourceFromIdeaRequest(title="t", language="de").language is None
    assert SourceFromIdeaRequest(title="t").language is None
    # A non-string is still a bad request: the validator normalizes locales, it does
    # not paper over a client sending the wrong type.
    with pytest.raises(ValueError):
        SourceFromIdeaRequest(title="t", language=3)


@pytest.mark.parametrize("name", sorted(CREATION_PROMPTS))
def test_english_appends_the_directive_without_touching_the_prompt(name: str):
    prompt = CREATION_PROMPTS[name]
    composed = with_language(prompt, "en")

    assert composed.startswith(prompt.rstrip())
    assert "ENGLISH" in composed
    # The rule has to be the last thing before the user turn: that is where a tie with
    # the prompt's own "write in the language of the source material" gets broken.
    assert composed.rstrip().splitlines()[-1].startswith("OUTPUT LANGUAGE:")


def test_the_user_prompts_name_the_language_too():
    """The system directive is not alone against a prompt body that says otherwise."""
    assert build_source_prompt(title="T", idea="I", language="en").rstrip().endswith(
        "Escribe el documento fuente en ingles."
    )
    assert (
        "Escribe el documento fuente de este punto en ingles."
        in build_node_source_prompt(
            course_title="C",
            course_idea="I",
            node_title="N",
            summary="S",
            outcome="O",
            language="en",
        )
    )
    # The schema designer's rule 6 forbids translating in so many words, so the
    # override names the rule it replaces.
    schema_prompt = build_schema_prompt([], {}, ["Uno"], language="en")
    assert "en ingles" in schema_prompt
    assert "sustituye la regla 6" in schema_prompt


# --------------------------------------------------------------------------------------
# Which language a course asks for
# --------------------------------------------------------------------------------------
def test_a_stored_default_language_is_read_as_silence():
    """``courses.language`` is ``NOT NULL DEFAULT 'es'``, so it always says something.

    Taking a defaulted ``'es'`` as a request would append the directive to every prompt
    of every existing course: new fixture keys everywhere, and a course built from an
    English manual suddenly being translated. Only a language that differs from what
    the prompts already do unprompted counts as an instruction.
    """
    assert ambient_language(DEFAULT_LANGUAGE) is None
    assert ambient_language("es-ES") is None
    assert ambient_language("en") == "en"
    assert ambient_language(None) is None


def test_an_explicit_request_beats_the_course_and_a_missing_column_is_not_a_crash():
    english_course = SimpleNamespace(language="en")
    spanish_course = SimpleNamespace(language="es")

    assert language_for_course(english_course) == "en"
    assert language_for_course(spanish_course) is None
    # Explicit wins outright, default or not: somebody typed it.
    assert language_for_course(english_course, explicit="es") == "es"
    assert language_for_course(spanish_course, explicit="en-US") == "en"
    # Migration 0037 adds the column; this code runs before and after it.
    assert language_for_course(SimpleNamespace()) is None


def test_the_deterministic_node_briefing_has_english_headings():
    """No model involved, so nothing else can translate these four strings."""
    node = SimpleNamespace(
        title="Cross contamination", summary="Keep utensils apart.", outcome="Avoid it."
    )
    course = SimpleNamespace(title="Allergens", description="The 14", language="en")

    text = seed_node_source(course=course, node=node)

    assert "## Outcome" in text
    assert "## What it covers" in text
    assert "## Course" in text
    assert "Resultado" not in text


def test_the_spanish_node_briefing_is_unchanged():
    node = SimpleNamespace(
        title="Contaminacion cruzada", summary="Separa los utensilios.", outcome="Evitarla."
    )
    course = SimpleNamespace(title="Alergenos", description="Los 14", language="es")

    text = seed_node_source(course=course, node=node)

    assert "## Resultado" in text
    assert "## Que cubre" in text
    assert "## Curso" in text


# --------------------------------------------------------------------------------------
# The language reaches the model on the creation path
# --------------------------------------------------------------------------------------
class ScriptedLLM:
    """Returns a fixed body and records exactly what it was asked."""

    model = "fixture/scripted"

    def __init__(self, body: str) -> None:
        self.body = body
        self.system: str | None = None
        self.user: str | None = None

    async def complete(self, system_prompt: str, user_prompt: str, **_kwargs) -> str:
        self.system = system_prompt
        self.user = user_prompt
        return self.body

    async def complete_with_usage(self, system_prompt: str, user_prompt: str, **_kwargs):
        self.system = system_prompt
        self.user = user_prompt
        return self.body, Usage(tokens_in=10, tokens_out=5)


class FakeRepo:
    """Enough of ``DocumentRepository`` for the service, with the rows in a list."""

    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []

    async def create(self, **kwargs) -> SimpleNamespace:
        row = SimpleNamespace(id=uuid.uuid4(), **kwargs)
        self.rows.append(row)
        return row

    async def update(self, doc, **kwargs) -> SimpleNamespace:
        for key, value in kwargs.items():
            setattr(doc, key, value)
        return doc


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from src.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


async def test_the_requested_language_reaches_the_source_writer(upload_dir: Path):
    """The one call that decides the language of the whole course."""
    llm = ScriptedLLM(GOOD_SOURCE)
    await DocumentService(FakeRepo()).create_from_idea(
        org_id=ORG_ID,
        created_by=USER_ID,
        title="How we learn",
        idea="Attention and memory",
        llm=llm,
        language="en",
    )

    assert (llm.system or "").startswith(SOURCE_WRITER_SYSTEM.rstrip())
    assert "ENGLISH" in (llm.system or "")
    assert (llm.user or "").rstrip().endswith("Escribe el documento fuente en ingles.")


async def test_no_requested_language_sends_the_prompt_it_always_sent(upload_dir: Path):
    llm = ScriptedLLM(GOOD_SOURCE)
    await DocumentService(FakeRepo()).create_from_idea(
        org_id=ORG_ID,
        created_by=USER_ID,
        title="Como aprendemos",
        idea="Atencion y memoria",
        llm=llm,
    )

    assert llm.system == SOURCE_WRITER_SYSTEM


async def test_the_node_drafter_follows_the_course_language():
    """Per-node briefs run in a background task that only has the course row."""
    llm = ScriptedLLM("## Cross contamination\n\n" + "Useful detail. " * 20)
    node = SimpleNamespace(
        id=uuid.uuid4(),
        title="Cross contamination",
        summary="Keep utensils apart.",
        outcome="Avoid it.",
    )
    course = SimpleNamespace(
        title="Allergens", description="The 14", outcome=None, language="en"
    )

    await ConfiguredKnowledgePackGenerator(llm).draft_source(course=course, node=node)

    assert (llm.system or "").startswith(NODE_SOURCE_WRITER_SYSTEM.rstrip())
    assert "ENGLISH" in (llm.system or "")


async def test_a_spanish_course_drafts_with_the_untouched_prompt():
    llm = ScriptedLLM("## Contaminacion cruzada\n\n" + "Detalle util. " * 20)
    node = SimpleNamespace(
        id=uuid.uuid4(),
        title="Contaminacion cruzada",
        summary="Separa los utensilios.",
        outcome="Evitarla.",
    )
    course = SimpleNamespace(
        title="Alergenos", description="Los 14", outcome=None, language="es"
    )

    await ConfiguredKnowledgePackGenerator(llm).draft_source(course=course, node=node)

    assert llm.system == NODE_SOURCE_WRITER_SYSTEM
