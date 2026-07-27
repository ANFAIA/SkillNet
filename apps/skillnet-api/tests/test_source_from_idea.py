"""Creating a course "desde cero": the source document is written, not uploaded.

The wizard has advertised "Desde cero — Define el tema y generamos el contenido con IA"
since v1 and it did not work: every stage of generation requires a `source_document_id`,
so the creator got *"A source document is required"* after typing a title.

The fix synthesises the source and then runs the ordinary pipeline, which means the
thing worth testing is not the generation — that is already covered — but the seam:
that what comes out is an ordinary `Document` nothing downstream has to special-case,
and that the one thing which *is* different about it cannot be lost.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.exceptions import AppError, ValidationError
from src.llm.prompts.source import SOURCE_WRITER_SYSTEM, build_source_prompt
from src.models import DocumentOrigin, DocumentStatus
from src.services.document_service import DocumentService, _strip_code_fence

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

GOOD_SOURCE = "\n\n".join(
    [
        "## Que es una sinapsis",
        "El punto de contacto entre dos neuronas. " + "Detalle util. " * 20,
        "## Neurotransmisores principales",
        "Dopamina, serotonina, acetilcolina. " + "Detalle util. " * 20,
    ]
)


class ScriptedLLM:
    """Returns a fixed body and records exactly what it was asked."""

    model = "fixture/scripted"

    def __init__(self, body: str) -> None:
        self.body = body
        self.system: str | None = None
        self.user: str | None = None
        self.kwargs: dict | None = None

    async def complete(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        self.system = system_prompt
        self.user = user_prompt
        self.kwargs = kwargs
        return self.body


class FakeRepo:
    """Enough of `DocumentRepository` for the service, with the rows kept in a list."""

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


async def _create(llm: ScriptedLLM, *, title: str = "Introduccion neurociencia", idea: str = ""):
    service = DocumentService(FakeRepo())
    return service, await service.create_from_idea(
        org_id=ORG_ID, created_by=USER_ID, title=title, idea=idea, llm=llm
    )


# --------------------------------------------------------------------------------------
# The seam: what comes out is an ordinary document
# --------------------------------------------------------------------------------------
async def test_the_synthesised_source_is_an_ordinary_markdown_document(upload_dir: Path):
    """`file_type='md'` and a real file on disk, because that is what makes the rest of
    the system able to ignore where the text came from: `parse_document` already handles
    `md`, so ingestion, chunking, embedding and retrieval all run unchanged."""
    _, doc = await _create(ScriptedLLM(GOOD_SOURCE))

    assert doc.file_type == "md"
    assert doc.status == DocumentStatus.PENDING
    assert doc.title == "Introduccion neurociencia"
    stored = Path(doc.storage_path)
    assert stored.is_file()
    # `.strip()`ped: models routinely pad the answer with a trailing newline or space,
    # and that padding would otherwise be the document's last chunk.
    written = stored.read_text(encoding="utf-8")
    assert written == GOOD_SOURCE.strip()
    assert doc.size_bytes == len(written.encode("utf-8"))


async def test_the_origin_says_the_model_wrote_it(upload_dir: Path):
    """The one field that must never be lost. A compliance course whose source silently
    turned out to be invented is the failure this product exists to avoid."""
    _, doc = await _create(ScriptedLLM(GOOD_SOURCE))
    assert doc.origin is DocumentOrigin.GENERATED


async def test_an_upload_is_still_uploaded(upload_dir: Path):
    """The column defaults the other way, so nothing that predates this path is
    mislabelled by it."""
    service = DocumentService(FakeRepo())
    doc = await service.create_document(
        org_id=ORG_ID, uploaded_by=USER_ID, filename="manual.md", content=b"# Manual\n"
    )
    assert getattr(doc, "origin", DocumentOrigin.UPLOADED) is DocumentOrigin.UPLOADED


# --------------------------------------------------------------------------------------
# The prompt carries the creator's brief, and the guardrails
# --------------------------------------------------------------------------------------
async def test_the_creators_description_reaches_the_model(upload_dir: Path):
    llm = ScriptedLLM(GOOD_SOURCE)
    await _create(llm, idea="Nivel introductorio, sin matematicas.")

    assert llm.system == SOURCE_WRITER_SYSTEM
    assert "Introduccion neurociencia" in (llm.user or "")
    assert "Nivel introductorio, sin matematicas." in (llm.user or "")


async def test_an_empty_description_is_stated_rather_than_left_blank(upload_dir: Path):
    """A title alone is a thin brief but a legitimate one — the wizard does not require
    the description. Sending an empty section would leave the model guessing what the
    silence means."""
    llm = ScriptedLLM(GOOD_SOURCE)
    await _create(llm, idea="   ")

    assert "no ha dado mas detalle que el titulo" in (llm.user or "")


def test_the_prompt_forbids_inventing_an_organisation_or_a_legal_citation():
    """The two hallucinations that would matter most here, and the reason this is the
    riskiest prompt in the product: it is the only one whose output cannot be checked
    against a document, because it *is* the document."""
    assert "No inventes el nombre de ninguna empresa" in SOURCE_WRITER_SYSTEM
    assert "No cites articulos" in SOURCE_WRITER_SYSTEM
    # Markdown headings are not cosmetic: `chunk_sections` keys chunks on them and the
    # v2 designer picks node sources from the heading list.
    assert "##" in SOURCE_WRITER_SYSTEM


def test_the_builder_always_asks_for_the_document():
    prompt = build_source_prompt(title="Alergenos", idea="los 14 obligatorios")
    assert prompt.rstrip().endswith("Escribe el documento fuente.")


# --------------------------------------------------------------------------------------
# Failure is refused, not stored
# --------------------------------------------------------------------------------------
async def test_a_refusal_or_an_empty_answer_does_not_become_a_course(upload_dir: Path):
    """Better a 502 the creator can retry than a course built on one apologetic line."""
    with pytest.raises(AppError) as excinfo:
        await _create(ScriptedLLM("Lo siento, no puedo ayudarte con eso."))
    assert excinfo.value.code == "SOURCE_GENERATION_FAILED"


async def test_a_blank_title_is_rejected_before_the_model_is_called(upload_dir: Path):
    llm = ScriptedLLM(GOOD_SOURCE)
    with pytest.raises(ValidationError):
        await _create(llm, title="   ")
    assert llm.system is None, "the model must not be called for an empty request"


# --------------------------------------------------------------------------------------
# The fence models add about a third of the time
# --------------------------------------------------------------------------------------
def test_a_wrapping_code_fence_is_removed():
    assert _strip_code_fence("```markdown\n## Uno\ntexto\n```") == "## Uno\ntexto"
    assert _strip_code_fence("```\n## Uno\n```") == "## Uno"


def test_a_fence_inside_the_document_is_left_alone():
    """Only a fence wrapping the *whole* answer is an artefact. One in the middle is
    content — a source about, say, configuring a till may legitimately contain one."""
    body = "## Uno\n\n```bash\nls -la\n```\n\n## Dos\n\ntexto"
    assert _strip_code_fence(body) == body
