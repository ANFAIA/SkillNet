"""What the node's material is *shaped* like, decided before a token is spent.

Why this module exists
======================

On 2026-07-27 the first node of the seeded ``Alergenos`` course was served to a real
learner as four valid blocks: a lead line, a paragraph listing all fourteen mandatory
allergens separated by commas, a ``Callout``, and a closing paragraph. The render passed
every check the pipeline had — ``status='ready'``, the gate clean, the contract rules
satisfied — and it was the wrong screen. Fourteen items are a **table**, and the model had
no way of knowing that, because nothing in the pipeline had looked at the material.

Two measurements frame the fix, and they are the *same* defect seen from both sides:

* Served: fourteen items flattened into one ``TextContent``. Three of the nine emittable
  blocks were used across the whole ``node_renders`` table.
* Rejected: on ``alergenos-hosteleria`` the model instead emitted **19 components** and on
  ``atencion-reclamaciones`` 23 declarations, both refused by rule 4 — one block per item.

So the model oscillates between "N items as one paragraph" and "N items as N blocks", and
never finds "N items as one ``Table``". ``SkillNet 15`` names all three options in one
sentence and lists the paragraph among them, which is the cheapest to write and the one it
picks. Telling it after the fact costs a repair round trip; on Groq's free tier that round
trip measured **24.7 s**, because the two calls together blow the tokens-per-minute quota.

What this module does about it
==============================

It reads the node's own source and reports, deterministically and for free, the structures
that are actually in there: an enumeration of N things, a labelled list, an ordered
procedure, a numeric series. ``build_ui_prompt`` turns those into instructions naming the
block, so the shape decision is made **from the content** instead of being inferred by an
8B model from the word ``explanation``.

This is the *classify* half of Curio's "classify + populate, never author markup", done
with a regex instead of a model call. A call was the obvious alternative and it is the
wrong one here: the thing that hurts on the free tier is tokens per minute, and a second
call to choose a shape would spend the quota that the generation itself needs.

What it deliberately does not do
================================

* **No ``Callout`` detector.** Prohibitions are trivially detectable and ``Callout`` is
  already one of the three blocks the model over-uses. A hint that fires on every
  compliance document would reinforce the bias this module exists to break.
* **No invented data.** A signal reports what the source *has*. ``SkillNet 13`` forbids
  inventing figures, and a hint that asked for a ``Chart`` the source cannot fill would be
  asking the model to break it.
* **No per-learner adaptation.** Every signal here is a property of the node, identical for
  everyone who opens it. That is what keeps this compatible with the calibration period of
  §6.4: the interface may not move under a learner who is still building a mental map, and
  a shape derived from the material does not move — it is the same shape for every learner
  and on every visit.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

# --- thresholds ---------------------------------------------------------------------
#
# Every one of these is a false-positive guard, measured against the ten briefs of
# ``scripts/quality_bench.py`` plus the two seeded courses. The failure mode to avoid is
# not "missed a table"; it is "told the model to build a table out of ordinary prose",
# because a hint the material cannot support sends it either to invent rows or to fight
# the instruction.

#: Items needed before a run of short fragments is a list rather than terse writing.
MIN_ENUM_ITEMS = 4
#: A fragment longer than this is a sentence, and a sentence ends the run.
MAX_ENUM_ITEM_CHARS = 80
#: ...and the run as a whole has to be *mostly* short, not just under the ceiling. Ordinary
#: prose clears 80 chars on individual sentences but never averages 40 over four in a row.
MAX_ENUM_MEAN_CHARS = 40

#: An inline ``a, b, c, ... y z`` run. Items are shorter than in a fragment run because a
#: comma-separated item is a noun phrase, never a clause.
MAX_INLINE_ITEM_CHARS = 60

MIN_LABELLED_ROWS = 3
MIN_PROCEDURE_STEPS = 3
MIN_SERIES_POINTS = 3

#: A labelled row's value has to *be* a figure, not merely contain one. ``"4 grados C"`` is
#: a data point; ``"pantalla facial completa, no solo gafas. Guantes anticorte nivel 5"``
#: has a ``5`` in it and is a sentence. Measured on ``epi-taller``, which without this cap
#: was reported as a three-point numeric series and would have been sent to a ``Chart``.
MAX_SERIES_VALUE_CHARS = 30

#: Only the first few hints travel. The length budget allows 3-5 blocks, so a fourth
#: instruction would be asking for a screen the validator refuses.
MAX_HINTS = 2


# --- signals ------------------------------------------------------------------------


@dataclass(frozen=True)
class ShapeSignal:
    """One structure found in the source, and the kit block that renders it."""

    #: ``enumeration`` | ``labelled_list`` | ``procedure`` | ``numeric_series``
    kind: str
    #: How many items/rows/steps/points were counted. Travels into the prompt: "14" is a
    #: far stronger instruction than "several".
    count: int
    #: The block this becomes. Always one name from the frozen kit (§5.3).
    block: str
    #: The block to use instead when the screen is a ``chart``.
    chart_block: str = ""

    def instruction(self, ui_format: str = "explanation") -> str:
        """The prompt line, naming the block and forbidding the two known wrong answers."""
        block = (
            self.chart_block
            if self.chart_block and ui_format == "chart"
            else self.block
        )
        if self.kind == "enumeration":
            # "unos", because the count is pieces of text and an item occasionally holds
            # two things ("altramuces y moluscos"). Asking for exactly N rows would make
            # the model pad or split to hit a number the source does not really state.
            # The one-column form is written out because the model got it wrong twice on
            # the real allergen node: told to use a single column it emitted
            # ``Table(["Alergeno"], [[...14 celdas...]])`` — one row instead of fourteen.
            # ``SkillNet 3`` already says rows is an array of arrays; with one column that
            # is counter-intuitive enough to need the literal shape.
            return (
                f"La fuente enumera una lista larga, de unos {self.count} elementos. Eso "
                f"es UN bloque {block} con UNA FILA POR ELEMENTO. Si la fuente da un dato "
                "de cada elemento, dos columnas; si no, una sola, y entonces cada fila es "
                'un array de una celda: Table(["Alergeno"], [["Gluten"], ["Huevos"]]). '
                "NO los pongas separados por comas dentro de un TextContent, y NO hagas "
                "un bloque por elemento."
            )
        if self.kind == "labelled_list":
            return (
                f"La fuente da {self.count} pares de etiqueta y valor. Eso es UN bloque "
                f"{block} de dos columnas, con la etiqueta en la primera. NO lo cuentes "
                "en prosa ni hagas un bloque por par."
            )
        if self.kind == "procedure":
            return (
                f"La fuente describe un procedimiento de {self.count} pasos en orden. "
                f"Usa StepByStepReveal si cada paso necesita explicacion, o StepSequence "
                "si son acciones breves sin explicacion. Cierra con DragOrder para que "
                "el aprendiz ordene los pasos. NO lo narres en un parrafo."
            )
        if self.kind == "numeric_series":
            return (
                f"La fuente da {self.count} valores numericos comparables. Eso es UN "
                f"bloque {block} con esas cifras EXACTAS, sin redondear y sin anadir "
                "ninguna que no este en la fuente."
            )
        return ""  # pragma: no cover - the four kinds above are the closed set


@dataclass(frozen=True)
class ShapePlan:
    """Everything the material said about its own shape."""

    signals: tuple[ShapeSignal, ...] = ()
    #: Whether the source carries digits at all — the honest input to the ``chart`` rule.
    has_numbers: bool = False

    def __bool__(self) -> bool:
        return bool(self.signals)

    @property
    def blocks(self) -> tuple[str, ...]:
        """The kit blocks this material asks for, in order of confidence."""
        return tuple(dict.fromkeys(signal.block for signal in self.signals))

    def hints(self, ui_format: str = "explanation") -> tuple[str, ...]:
        """The prompt lines, capped at :data:`MAX_HINTS`."""
        return tuple(
            signal.instruction(ui_format) for signal in self.signals[:MAX_HINTS]
        )

    @property
    def summary(self) -> str:
        """One line for a log or a rationale, never for a prompt."""
        if not self.signals:
            return "sin estructura detectada"
        return ", ".join(f"{s.kind}x{s.count}->{s.block}" for s in self.signals)


# --- text helpers ---------------------------------------------------------------------


def fold(text: str) -> str:
    """Lowercase and strip accents, so ``Fase``/``fase`` and ``párrafo``/``parrafo`` match.

    Real customer documents carry accents; the bench corpus does not. A detector that only
    worked on one of the two would pass its tests and miss production.
    """
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


#: A fragment that is only a number, a bullet or an ordinal is punctuation, not an item.
#: ``"1. Plazo. El cliente dispone..."`` splits to ``["1", "Plazo", "El cliente..."]`` and
#: without this the ``"1"`` counts as a very short item and drags the mean down.
_NOISE_FRAGMENT_RE = re.compile(r"^[\W\d_]*$")

#: Paragraph break. Runs are counted **inside** a paragraph: a heading followed by the
#: first three sentences of a section is not a list, and every false positive found while
#: writing this module was of exactly that shape.
_PARAGRAPH_RE = re.compile(r"\n\s*\n")

#: Sentence/clause break inside a paragraph. Semicolons count: ``"a; b; c"`` is a list.
_FRAGMENT_RE = re.compile(r"[.;]+")

#: A labelled row **must** carry a bullet marker, and that is a deliberate loss of recall.
#:
#: Without the marker the pattern matches any line holding a colon, and a paragraph is a
#: line: measured on ``prevencion-riesgos`` it collected ``"Factores que agravan el
#: riesgo: ..."`` and ``"5. No girar el tronco con la carga en alto: mover los pies"`` and
#: reported a three-row table that does not exist. The asymmetry is the reason to accept
#: the loss — a missed hint costs nothing (the prompt falls back to what it says today),
#: while a hint the material cannot support sends the model to invent rows.
_LABELLED_RE = re.compile(
    r"^[ \t]*[-*•·]\s*([^:\n]{2,60}?)\s*:\s*(\S[^\n]*)$", re.MULTILINE
)
_NUMBERED_RE = re.compile(r"^[ \t]*(\d{1,2})[.)]\s+\S", re.MULTILINE)
#: ``P - Quitar el Pasador`` — the mnemonic-procedure shape (the extintor brief's PAS).
_LETTER_STEP_RE = re.compile(r"^[ \t]*([A-Za-z])\s*[-–]\s+\S", re.MULTILINE)
_WORD_STEP_RE = re.compile(r"\b(?:paso|fase|etapa)\s+(\d{1,2})\b")
_DIGIT_RE = re.compile(r"\d")


def _fragments(paragraph: str) -> list[str]:
    """A paragraph split into clause-sized pieces, noise dropped."""
    pieces = (piece.strip() for piece in _FRAGMENT_RE.split(paragraph))
    return [
        piece
        for piece in pieces
        if piece and not _NOISE_FRAGMENT_RE.match(piece)
    ]


# --- detectors --------------------------------------------------------------------


def _detect_enumeration(source: str) -> ShapeSignal | None:
    """The longest run of consecutive short fragments inside one paragraph.

    This is the ``Alergenos`` shape and the reason the module exists. The source reads
    ``"Cereales con gluten (...). Crustaceos. Huevos. Pescado. Cacahuetes. Soja. ..."`` —
    fourteen fragments averaging 22 characters, ended by an 88-character sentence about
    which products carry them. A run is only a list if it is both **long** and **terse**,
    which is what the two thresholds test for separately.
    """
    best = 0
    for paragraph in _PARAGRAPH_RE.split(source):
        run: list[int] = []
        for fragment in _fragments(paragraph):
            length = len(fragment)
            if length <= MAX_ENUM_ITEM_CHARS:
                run.append(length)
                continue
            best = max(best, _score_run(run))
            run = []
        best = max(best, _score_run(run))
    if best < MIN_ENUM_ITEMS:
        return None
    return ShapeSignal(kind="enumeration", count=best, block="Table")


def _score_run(run: Sequence[int]) -> int:
    """A run's item count, or 0 when the run is prose that happens to be short."""
    if len(run) < MIN_ENUM_ITEMS:
        return 0
    if sum(run) / len(run) > MAX_ENUM_MEAN_CHARS:
        return 0
    return len(run)


#: A Spanish list closes with ``y``/``e``/``o``/``u`` before its last item. Used as the
#: evidence that a comma run is an enumeration and not a sentence with commas in it.
_LIST_TERMINATOR_RE = re.compile(r"\s(?:y|e|o|u)\s")


def _detect_inline_enumeration(source: str) -> ShapeSignal | None:
    """``"Los 14 alergenos son: cereales con gluten, crustaceos, huevos, ..."``.

    The other enumeration shape, and the one the seeded course and the bench brief spell
    differently: the fourteen allergens are written as fourteen sentences in the customer
    document and as one comma-separated sentence in the brief. A detector that only knew
    the first would have missed the exact screen this module was written for.

    Commas are the most common character in prose, so two independent pieces of evidence
    are required before a comma run counts: the run is **introduced** (a colon precedes
    it) or **closed** the way Spanish closes a list (``... y <last>``), *and* the items are
    short noun phrases rather than clauses.
    """
    best = 0
    for paragraph in _PARAGRAPH_RE.split(source):
        for fragment in _fragments(paragraph):
            head, sep, tail = fragment.rpartition(":")
            candidate = tail if sep else fragment
            pieces = [piece.strip() for piece in candidate.split(",")]
            pieces = [piece for piece in pieces if piece]
            if len(pieces) < MIN_ENUM_ITEMS:
                continue
            if any(len(piece) > MAX_INLINE_ITEM_CHARS for piece in pieces):
                continue
            if sum(len(p) for p in pieces) / len(pieces) > MAX_ENUM_MEAN_CHARS:
                continue
            introduced = bool(sep and head.strip())
            closed = bool(_LIST_TERMINATOR_RE.search(fold(pieces[-1])))
            if introduced or closed:
                best = max(best, len(pieces))
    if best < MIN_ENUM_ITEMS:
        return None
    return ShapeSignal(kind="enumeration", count=best, block="Table")


def _labelled_rows(source: str) -> list[tuple[str, str]]:
    """``- Camara de carne: 4 grados C`` → ``("Camara de carne", "4 grados C")``.

    Only rows on their **own line** count. A colon mid-paragraph is punctuation
    (``"La consigna es siempre: avisar, evacuar..."``), and treating it as a table row is
    how a detector starts inventing structure that is not there.
    """
    rows: list[tuple[str, str]] = []
    for match in _LABELLED_RE.finditer(source):
        label, value = match.group(1).strip(), match.group(2).strip()
        if label and value:
            rows.append((label, value))
    return rows


def _detect_labelled(source: str) -> ShapeSignal | None:
    rows = _labelled_rows(source)
    if len(rows) < MIN_LABELLED_ROWS:
        return None
    return ShapeSignal(kind="labelled_list", count=len(rows), block="Table")


def _detect_numeric_series(source: str) -> ShapeSignal | None:
    """Labelled rows whose value is a figure — the only honest basis for a ``Chart``.

    Requires the *values* to carry digits, not the paragraph around them: a section that
    happens to cite ``Reglamento 1169/2011`` has digits and no series.
    """
    points = [
        (label, value)
        for label, value in _labelled_rows(source)
        if _DIGIT_RE.search(value) and len(value) <= MAX_SERIES_VALUE_CHARS
    ]
    if len(points) < MIN_SERIES_POINTS:
        return None
    return ShapeSignal(
        kind="numeric_series", count=len(points), block="Table", chart_block="Chart"
    )


def _detect_procedure(source: str) -> ShapeSignal | None:
    """Ordered steps: ``1.`` lines, ``Paso N``/``Fase N``, or the ``P - ...`` mnemonic."""
    numbered = _NUMBERED_RE.findall(source)
    if len(numbered) >= MIN_PROCEDURE_STEPS:
        return ShapeSignal(
            kind="procedure", count=len(numbered), block="StepSequence"
        )
    worded = _WORD_STEP_RE.findall(fold(source))
    if len(worded) >= MIN_PROCEDURE_STEPS:
        return ShapeSignal(kind="procedure", count=len(worded), block="StepSequence")
    lettered = _LETTER_STEP_RE.findall(source)
    if len(lettered) >= MIN_PROCEDURE_STEPS:
        return ShapeSignal(kind="procedure", count=len(lettered), block="StepSequence")
    return None


# --- the plan ----------------------------------------------------------------------


#: A paragraph that is one short line without a closing period is a section heading.
#: Matches ``"Marco legal"`` and ``"Contaminacion cruzada en el obrador"`` and not the
#: bodies under them, which are multi-sentence and end in '.'.
MAX_HEADING_CHARS = 80


def _looks_like_heading(paragraph: str) -> bool:
    text = paragraph.strip()
    return (
        bool(text)
        and "\n" not in text
        and len(text) <= MAX_HEADING_CHARS
        and not text.endswith((".", ":", ";"))
    )


def focus_on_headings(source: str, headings: Sequence[str]) -> str:
    """The sections of ``source`` that belong to this node, or all of it when unsure.

    A document of five pages or fewer travels **whole** into every node's prompt
    (``load_source_context`` takes the ``full_text`` branch), so all three nodes of the
    seeded ``Alergenos`` course see the same text. Without this, the node about
    cross-contamination would be told to build a table of fourteen allergens, because the
    allergens are in the source it was handed — true, and not what that node is about.

    ``course_nodes.source_headings`` is the node's own claim on part of the document and
    the same key retrieval uses for the chunked branch, so it is the honest scope. When
    nothing matches, the whole source is returned: a hint drawn from too much text is a
    smaller error than no hint at all, and the thresholds still have to clear.
    """
    wanted = [fold(h).strip() for h in headings if h and h.strip()]
    if not wanted or not source.strip():
        return source

    paragraphs = _PARAGRAPH_RE.split(source)
    kept: list[str] = []
    collecting = False
    for paragraph in paragraphs:
        if _looks_like_heading(paragraph):
            folded = fold(paragraph).strip()
            collecting = any(
                folded in heading or heading in folded for heading in wanted
            )
            if collecting:
                kept.append(paragraph)
            continue
        if collecting:
            kept.append(paragraph)
    return "\n\n".join(kept) if kept else source


def analyze_shape(
    *, source_context: str = "", summary: str = "", headings: Sequence[str] = ()
) -> ShapePlan:
    """Read the node's material and report the structures in it.

    ``summary`` is appended because a node whose document did not survive retrieval still
    has its own one-line description, and an enumeration is sometimes stated there. The
    source dominates: it is the only text the generator is allowed to draw facts from.

    Ordering is by **specificity**, not by count. A numeric series is a labelled list with
    figures in it, and a labelled list is an enumeration with two columns; reporting the
    weaker reading of the same paragraph as a second hint would spend the budget saying
    the same thing twice, so each paragraph shape contributes once.
    """
    scoped = focus_on_headings(source_context, headings)
    text = "\n\n".join(part for part in (scoped, summary) if part.strip())
    if not text.strip():
        return ShapePlan()

    ordered: list[ShapeSignal] = []
    series = _detect_numeric_series(text)
    labelled = _detect_labelled(text)
    procedure = _detect_procedure(text)
    # The two spellings of the same structure; the longer run is the better evidence.
    runs = [
        signal
        for signal in (_detect_enumeration(text), _detect_inline_enumeration(text))
        if signal is not None
    ]
    enumeration = max(runs, key=lambda signal: signal.count) if runs else None

    # A numeric series and a labelled list are the same rows read twice: keep the stronger.
    table_signal = series or labelled
    if table_signal is not None:
        ordered.append(table_signal)
    if procedure is not None:
        ordered.append(procedure)
    # An enumeration only adds something when no table shape was found: the fourteen
    # allergens are a run of fragments and produce no labelled rows at all, which is
    # exactly the case this last branch is for.
    if enumeration is not None and table_signal is None:
        ordered.append(enumeration)

    return ShapePlan(
        signals=tuple(ordered), has_numbers=bool(_DIGIT_RE.search(scoped))
    )


# --- format refinement ---------------------------------------------------------------

#: Formats whose screen is only possible when the source carries figures (§4.2, rule 1 of
#: ``FORMAT_DECIDER_SYSTEM``).
_NEEDS_NUMBERS = "chart"


def refine_format(
    default_format: str, plan: ShapePlan, *, criticality: str = "recommended"
) -> tuple[str, str]:
    """Correct a hand-written ``default_ui_format`` the material flatly contradicts.

    Deliberately **narrow**, and the narrowness is the design. The obvious move after the
    ``Alergenos`` report was to re-derive the format from the content, and it is the wrong
    move: the screen the owner rejected was a *correct* ``explanation`` built out of the
    wrong blocks. Format is four coarse buckets and does not determine the shape; the
    blocks do, and those are handled by :func:`analyze_shape`. Swapping the bucket as well
    would churn the ``cache_key`` of every seeded node for no measured gain.

    So only the two cases where the declared format is **impossible** are corrected:

    * ``chart`` over a source with no figures. The generator would have to invent them,
      which ``SkillNet 13`` forbids, so the screen can only come out wrong or be refused.
      Outside calibration ``decide_formato`` already guards this by telling the model
      whether the source has figures; during calibration nothing did, and this closes it.
    * ``chart`` on a ``critical`` node, which ``FORMAT_DECIDER_SYSTEM`` forbids outright
      and which the calibration short-circuit was quietly bypassing.

    Returns ``(format, rationale)``; the rationale is stored, never prompted.
    """
    if default_format != _NEEDS_NUMBERS:
        return default_format, ""
    if criticality == "critical":
        return (
            "explanation",
            "el nodo es critical y un critical no se presenta solo como chart",
        )
    if not plan.has_numbers:
        return (
            "explanation",
            "la fuente no trae cifras representables y un chart tendria que inventarlas",
        )
    return default_format, ""


__all__ = [
    "MAX_ENUM_ITEM_CHARS",
    "MAX_ENUM_MEAN_CHARS",
    "MAX_HEADING_CHARS",
    "MAX_HINTS",
    "MAX_INLINE_ITEM_CHARS",
    "MAX_SERIES_VALUE_CHARS",
    "MIN_ENUM_ITEMS",
    "MIN_LABELLED_ROWS",
    "MIN_PROCEDURE_STEPS",
    "MIN_SERIES_POINTS",
    "ShapePlan",
    "ShapeSignal",
    "analyze_shape",
    "focus_on_headings",
    "fold",
    "refine_format",
]
