"""Tests for ``src/agents/runtime/shape.py`` — the content-shape analysis of §4.2.

The suite is organised around the two ways this module can be wrong, and they are not
equally bad:

* **A missed structure** costs nothing. The prompt falls back to what it said before and
  the model does what it did before.
* **An invented structure** is a bad screen. A hint saying "the source gives you five
  numeric values" when it does not sends the model either to invent them — which
  ``SkillNet 13`` forbids outright, in a compliance product — or to fight the instruction.

So the false-positive tests below are the load-bearing half, and every threshold in the
module has one. The texts are the real ones: the briefs of ``scripts/quality_bench.py``
and the seeded ``Alergenos`` document, not prose written to make a regex pass.
"""

from __future__ import annotations

import pytest

from src.agents.runtime.shape import (
    MAX_HINTS,
    ShapePlan,
    analyze_shape,
    focus_on_headings,
    fold,
    refine_format,
)

# --------------------------------------------------------------------------------------
# The material this module was written for
# --------------------------------------------------------------------------------------

#: The seeded customer document, spelled the way the real one is: the fourteen allergens
#: as fourteen short sentences, closed by a long one about which products carry them.
ALERGENOS_DOC = """\
Manual de alergenos e informacion al cliente

Marco legal

El Reglamento (UE) 1169/2011 y el Real Decreto 126/2015 obligan a informar de la presencia
de los catorce alergenos de declaracion obligatoria en cualquier alimento que se sirva sin
envasar. La responsabilidad de que esa informacion sea correcta es del establecimiento.

Los catorce alergenos de declaracion obligatoria

Cereales con gluten (trigo, centeno, cebada, avena, espelta, kamut). Crustaceos. Huevos.
Pescado. Cacahuetes. Soja. Leche, incluida la lactosa. Frutos de cascara (almendra,
avellana, nuez, anacardo, pistacho y similares). Apio. Mostaza. Granos de sesamo. Dioxido
de azufre y sulfitos en concentraciones superiores a 10 mg/kg. Altramuces. Moluscos. En La
Espiga, la masa madre, las empanadas y toda la bolleria llevan cereales con gluten.

Contaminacion cruzada en el obrador

La harina de trigo permanece en suspension en el aire hasta veinte minutos despues de
amasar, asi que un pedido sin gluten no se prepara justo despues de un amasado. Antes de
elaborar sin gluten se limpian a fondo superficie, amasadora y utensilios.
"""

#: The same fourteen items written inline, which is how the bench brief spells them. The
#: module has to find the list in both spellings or it would have missed the one screen it
#: was written for, depending on which document the customer happened to upload.
ALERGENOS_INLINE = (
    "Los 14 alergenos de declaracion obligatoria son: cereales con gluten, crustaceos, "
    "huevos, pescado, cacahuetes, soja, leche, frutos de cascara, apio, mostaza, granos "
    "de sesamo, dioxido de azufre y sulfitos, altramuces y moluscos."
)

TEMPERATURAS = """\
PLAN DE HIGIENE - CONTROL DE TEMPERATURAS (APPCC)

Temperaturas maximas de conservacion:
- Camara de refrigerado de carne: 4 grados C
- Camara de refrigerado de pescado: 2 grados C
- Camara de lacteos y postres: 6 grados C
- Congelador: -18 grados C
- Vitrina de servicio en caliente: 65 grados C minimo
"""

PROCEDIMIENTO = """\
Tecnica correcta:
1. Separar los pies a la anchura de los hombros, uno ligeramente adelantado.
2. Doblar las rodillas manteniendo la espalda recta, nunca doblar la espalda.
3. Agarrar la carga firmemente con las dos manos.
4. Levantar suavemente estirando las piernas, con la carga pegada al cuerpo.
"""

#: Ordinary compliance prose. Nothing in here is a list, a table or a series, and the whole
#: point of the thresholds is that this produces no hint at all.
PROSA = """\
PROTECCION DE DATOS - INSTRUCCIONES PARA PERSONAL DE ATENCION

Principio de minimizacion. Solo se piden los datos necesarios para la gestion concreta.
Para una reparacion en garantia hacen falta nombre, telefono y numero de serie: no hace
falta el DNI ni la fecha de nacimiento.

Consentimiento. Para enviar publicidad hace falta una casilla marcada activamente por el
cliente. Una casilla premarcada no es consentimiento valido. El consentimiento se puede
retirar en cualquier momento y hay que atender la retirada en el acto.
"""


# --------------------------------------------------------------------------------------
# The structures that are really there
# --------------------------------------------------------------------------------------


def test_the_fourteen_allergens_written_as_sentences_are_a_table() -> None:
    """The screen the owner rejected, from the document the customer actually uploaded."""
    plan = analyze_shape(source_context=ALERGENOS_DOC)

    assert plan.blocks == ("Table",)
    signal = plan.signals[0]
    assert signal.kind == "enumeration"
    # Fourteen items, and the long closing sentence must not be counted as a fifteenth.
    assert signal.count == 14


def test_the_fourteen_allergens_written_inline_are_the_same_table() -> None:
    plan = analyze_shape(source_context=ALERGENOS_INLINE)

    assert plan.blocks == ("Table",)
    assert plan.signals[0].kind == "enumeration"


def test_the_enumeration_hint_forbids_both_measured_wrong_answers() -> None:
    """One paragraph of commas and one block per item are the two failures on record.

    Served: the fourteen allergens as a comma-separated ``TextContent``. Rejected on the
    bench: 19 components, one per allergen. The hint has to close both, because closing
    only one is how the model moves from the first failure to the second.
    """
    hint = analyze_shape(source_context=ALERGENOS_DOC).hints()[0]

    assert "Table" in hint
    assert "separados por comas" in hint
    assert "un bloque por elemento" in hint


def test_labelled_rows_with_short_numeric_values_are_a_series() -> None:
    plan = analyze_shape(source_context=TEMPERATURAS)

    assert plan.signals[0].kind == "numeric_series"
    assert plan.signals[0].count == 5
    assert plan.has_numbers is True


def test_a_numeric_series_becomes_a_chart_only_on_a_chart_screen() -> None:
    """Same signal, different block: the kit has both and the format picks."""
    plan = analyze_shape(source_context=TEMPERATURAS)

    assert "Chart" in plan.hints("chart")[0]
    assert "Table" in plan.hints("explanation")[0]


def test_numbered_lines_are_a_step_sequence() -> None:
    plan = analyze_shape(source_context=PROCEDIMIENTO)

    assert "StepSequence" in plan.blocks
    assert plan.signals[0].count == 4


def test_a_mnemonic_procedure_is_a_step_sequence() -> None:
    """``P - ... / A - ... / S - ...`` is the extintor brief's shape."""
    source = (
        "Secuencia de uso (regla PAS):\n"
        "P - Quitar el Pasador de seguridad tirando de la anilla.\n"
        "A - Apuntar la boquilla a la base de la llama, no a las llamas.\n"
        "S - Presionar la maneta y barrer en zigzag.\n"
    )

    plan = analyze_shape(source_context=source)

    assert "StepSequence" in plan.blocks


def test_phase_words_are_a_procedure() -> None:
    source = (
        "Fase 1 - Escucha. Se deja hablar al cliente hasta el final.\n\n"
        "Fase 2 - Reformulacion. Se resume lo que ha dicho.\n\n"
        "Fase 3 - Disculpa por el efecto, no por la culpa.\n\n"
        "Fase 4 - Compromiso. Toda llamada se cierra con que, quien y cuando.\n"
    )

    plan = analyze_shape(source_context=source)

    assert "StepSequence" in plan.blocks


# --------------------------------------------------------------------------------------
# The structures that are not there — the half that protects the learner
# --------------------------------------------------------------------------------------


def test_ordinary_prose_produces_no_hint_at_all() -> None:
    plan = analyze_shape(source_context=PROSA)

    assert not plan
    assert plan.blocks == ()
    assert plan.hints() == ()


def test_a_colon_inside_a_sentence_is_not_a_table_row() -> None:
    """``"Factores que agravan el riesgo: ..."`` is a lead-in, not a two-column row.

    Measured while writing the module: without the bullet requirement this text reported a
    three-row table built out of one sentence and one numbered step.
    """
    source = (
        "5. No girar el tronco con la carga en alto: mover los pies.\n\n"
        "Factores que agravan el riesgo: carga voluminosa, suelo resbaladizo, giros.\n\n"
        "La consigna es siempre: avisar, evacuar y solo despues extinguir.\n"
    )

    kinds = {signal.kind for signal in analyze_shape(source_context=source).signals}

    assert "labelled_list" not in kinds


def test_an_incidental_number_in_a_long_value_is_not_a_data_point() -> None:
    """``epi-taller``: rows whose values are sentences that happen to contain figures.

    ``"Guantes anticorte nivel 5 y proteccion auditiva (85 dB es el limite)"`` has two
    numbers in it and is not a value anybody can plot. Reported as a series, this brief
    would have been sent to build a ``Chart`` out of glove ratings.
    """
    source = (
        "Por tarea:\n"
        "- Amolado y corte: pantalla facial completa, no solo gafas. Guantes anticorte "
        "nivel 5 y proteccion auditiva (tapones o cascos, 85 dB es el limite).\n"
        "- Soldadura: pantalla de soldadura con filtro DIN 11, mandil de cuero, polainas "
        "y guantes largos.\n"
        "- Manipulacion de quimicos: guantes de nitrilo y gafas de montura integral.\n"
    )

    plan = analyze_shape(source_context=source)

    assert plan.signals[0].kind == "labelled_list"
    assert plan.blocks == ("Table",)


def test_a_heading_plus_three_short_sentences_is_not_a_list() -> None:
    """Runs are counted inside a paragraph, so a section opening is not an enumeration."""
    source = (
        "MANUAL DE AUTOPROTECCION\n\n"
        "Tipo de extintor. Los extintores del local son de polvo ABC de 6 kg. Sirven "
        "para solidos, liquidos y gases. NO se usan sobre equipos electricos en tension "
        "por encima de 1.000 V ni sobre aceite de freidora, para el que hay una manta.\n"
    )

    kinds = {signal.kind for signal in analyze_shape(source_context=source).signals}

    assert "enumeration" not in kinds


def test_three_commas_are_not_an_enumeration() -> None:
    """``MIN_ENUM_ITEMS`` is 4: a sentence listing three things is a sentence."""
    source = "El fondo fijo es de 200 euros: 40 en monedas, 30 en calderilla y 80 en billetes."

    assert not analyze_shape(source_context=source)


def test_an_empty_source_is_not_an_error() -> None:
    assert analyze_shape(source_context="", summary="") == ShapePlan()


# --------------------------------------------------------------------------------------
# Scoping: a shared document must not hand every node the same hint
# --------------------------------------------------------------------------------------


def test_a_node_only_sees_its_own_section() -> None:
    """A document of <= 5 pages travels whole into every node's prompt.

    All three nodes of the seeded ``Alergenos`` course are handed the same text, so
    without scoping the cross-contamination node would be told to build a table of
    fourteen allergens — true of the source it received, and not what that node teaches.
    """
    catorce = analyze_shape(
        source_context=ALERGENOS_DOC,
        headings=["Los catorce alergenos de declaracion obligatoria", "Marco legal"],
    )
    cruzada = analyze_shape(
        source_context=ALERGENOS_DOC,
        headings=["Contaminacion cruzada en el obrador"],
    )

    assert catorce.blocks == ("Table",)
    assert cruzada.blocks == ()


def test_headings_that_match_nothing_fall_back_to_the_whole_source() -> None:
    """Re-ingestion renames a heading; a hint from too much text beats no hint."""
    plan = analyze_shape(
        source_context=ALERGENOS_DOC, headings=["Una seccion que ya no existe"]
    )

    assert plan.blocks == ("Table",)


def test_focus_keeps_the_body_under_the_heading() -> None:
    scoped = focus_on_headings(ALERGENOS_DOC, ["Contaminacion cruzada en el obrador"])

    assert "harina de trigo permanece en suspension" in scoped
    assert "Crustaceos" not in scoped


def test_focus_matches_regardless_of_accents_and_case() -> None:
    scoped = focus_on_headings(ALERGENOS_DOC, ["MARCO LEGAL"])

    assert "Reglamento (UE) 1169/2011" in scoped


def test_fold_strips_accents_and_case() -> None:
    assert fold("Contaminación Cruzada") == "contaminacion cruzada"


# --------------------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------------------


def test_no_more_hints_than_the_length_budget_allows() -> None:
    """The screen holds 3-5 blocks, so a third structural instruction cannot be obeyed."""
    plan = analyze_shape(source_context=TEMPERATURAS + "\n\n" + PROCEDIMIENTO)

    assert len(plan.signals) >= 2
    assert len(plan.hints()) <= MAX_HINTS


def test_a_shape_hint_never_displaces_the_lead_slot() -> None:
    """Rule 7 and the shape hint must not fight, because rule 7 wins and the render loses.

    Measured end to end on the real ``Los catorce alergenos obligatorios`` node: the model
    took the hint, opened the screen with the ``Table``, and was refused twice —
    ``format 'explanation' requires the first child of root to be a TextContent with
    variant='lead' or a Callout. Got Table`` — then fell back to the seed lesson. The hints
    are deliberately the last thing in the prompt, so they have to carry the ordering
    themselves.
    """
    from src.llm.prompts.runtime import build_ui_prompt

    plan = analyze_shape(source_context=ALERGENOS_DOC)

    for ui_format in ("explanation", "mixed"):
        prompt = build_ui_prompt(
            title="Los catorce alergenos",
            summary="S",
            ui_format=ui_format,
            shape_hints=plan.hints(ui_format),
        )
        assert "nunca el primero" in prompt, ui_format
        assert '"lead"' in prompt, ui_format

    # ``exercise`` has no lead slot (rule 7 does not apply), so the clause stays out.
    exercise = build_ui_prompt(
        title="T", summary="S", ui_format="exercise", shape_hints=plan.hints("exercise")
    )
    assert "nunca el primero" not in exercise


def test_the_repair_turn_repeats_the_shape_and_the_lead_rule() -> None:
    """The repair is the turn where "those 14 items are one Table" matters most."""
    from src.llm.prompts.runtime import build_repair_prompt

    plan = analyze_shape(source_context=ALERGENOS_DOC)
    prompt = build_repair_prompt(
        previous="root = Stack([t], \"md\")",
        errors=["rule 4: a spec holds at most 12 blocks (got 19)"],
        ui_format="explanation",
        shape_hints=plan.hints("explanation"),
    )

    assert "Table" in prompt
    assert "nunca el primero" in prompt


def test_the_same_rows_are_never_reported_twice() -> None:
    """A numeric series *is* a labelled list; naming both would spend the budget twice."""
    kinds = [signal.kind for signal in analyze_shape(source_context=TEMPERATURAS).signals]

    assert kinds.count("numeric_series") + kinds.count("labelled_list") == 1


# --------------------------------------------------------------------------------------
# refine_format: the two cases a hand-written default cannot survive
# --------------------------------------------------------------------------------------


def test_a_chart_over_a_source_with_no_figures_becomes_an_explanation() -> None:
    """The seeded ``Coordinacion con cocina y tiempos`` node, exactly.

    It is declared ``chart`` and its section writes every number as a word — "doce
    minutos", "dieciocho", "cinco minutos". There is not one digit to plot, so the
    generator could only have invented the series, which ``SkillNet 13`` forbids. Nothing
    caught this during calibration because nothing read the source.
    """
    source = (
        "El tiempo objetivo de salida es de doce minutos para los primeros y dieciocho "
        "para los segundos. Si cocina se retrasa mas de cinco minutos, se avisa a la mesa."
    )
    plan = analyze_shape(source_context=source)

    ui_format, reason = refine_format("chart", plan, criticality="recommended")

    assert ui_format == "explanation"
    assert "cifras" in reason


def test_a_critical_node_is_never_served_as_a_chart_alone() -> None:
    plan = analyze_shape(source_context=TEMPERATURAS)

    ui_format, reason = refine_format("chart", plan, criticality="critical")

    assert ui_format == "explanation"
    assert "critical" in reason


def test_a_chart_with_real_figures_is_left_alone() -> None:
    plan = analyze_shape(source_context=TEMPERATURAS)

    assert refine_format("chart", plan, criticality="recommended") == ("chart", "")


@pytest.mark.parametrize("declared", ["explanation", "exercise", "mixed"])
def test_every_other_declared_format_is_left_exactly_as_the_creator_wrote_it(
    declared: str,
) -> None:
    """The narrowness is the design.

    The screen the owner rejected was a *correct* ``explanation`` built out of the wrong
    blocks, so re-deriving the format would have churned the ``cache_key`` of every seeded
    node without fixing anything. Blocks are the knob; format is not.
    """
    plan = analyze_shape(source_context=ALERGENOS_DOC)

    assert refine_format(declared, plan, criticality="critical") == (declared, "")
