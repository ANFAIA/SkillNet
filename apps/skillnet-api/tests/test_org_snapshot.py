"""The admin's snapshot: the arithmetic, the text, and the line it must not cross.

Three groups, and the middle one is the reason the file exists at all.

1. **The facts.** Percentages, overdue deadlines and the completed-means-100% rule.
2. **The privacy allowlist.** ``learner_profiles`` is private to the employee (its own
   docstring says so); the admin sees training records and never the declared onboarding
   answers. That is enforced by reading this module's **AST** and asserting no forbidden
   column is ever touched, because "nobody added it" is a habit and this is a control.
3. **The rendering.** The exact bytes that reach the model, including the two things the
   model cannot infer: that every number is printed, and that a trimmed list says so.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from src.services import org_snapshot as snapshot_module
from src.services.org_snapshot import (
    FORBIDDEN_PROFILE_FIELDS,
    MAX_EMPLOYEES_LISTED,
    CourseFact,
    EmployeeFact,
    EnrolmentFact,
    OrgSnapshot,
    render_snapshot,
)

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def _snapshot(**overrides) -> OrgSnapshot:
    base = {
        "org_name": "Panaderia y Cafeteria La Espiga S.L.",
        "generated_at": NOW,
        "employees": (),
        "courses": (),
        "documents": (),
        "documents_total": 0,
        "employees_total": 0,
    }
    base.update(overrides)
    employees = base["employees"]
    if employees and not base["employees_total"]:
        base["employees_total"] = len(employees)
    return OrgSnapshot(**base)  # type: ignore[arg-type]


LUCIA = EmployeeFact(
    full_name="Lucia Fernandez Vila",
    role_title="Dependiente",
    hired_on=date(2023, 9, 4),
    enrolments=(
        EnrolmentFact(
            course_title="Alergenos e informacion al cliente",
            status="in_progress",
            done=2,
            total=5,
            unit="nodos",
            deadline=date(2026, 8, 15),
        ),
        EnrolmentFact(
            course_title="Manejo de caja",
            status="assigned",
            done=0,
            total=4,
            unit="lecciones",
            deadline=date(2026, 7, 1),
        ),
    ),
    skills=(("caja_tpv", "medium"), ("gestion_alergenos", "low")),
    nodes_mastered=2,
)

MARCOS = EmployeeFact(
    full_name="Marcos Iglesias Rey",
    role_title="Cocinero",
    enrolments=(
        EnrolmentFact(
            course_title="Alergenos e informacion al cliente",
            status="completed",
            done=5,
            total=5,
            unit="nodos",
            completed_on=date(2026, 7, 20),
        ),
    ),
    nodes_mastered=5,
)


# -- the facts ----------------------------------------------------------------------
def test_percent_is_rounded_from_the_counted_units() -> None:
    assert EnrolmentFact("C", "in_progress", done=2, total=5).percent == 40
    assert EnrolmentFact("C", "in_progress", done=1, total=3).percent == 33


def test_percent_is_none_when_the_course_has_no_units_to_count() -> None:
    """A course with no lessons and no nodes has no progress, and 0% would be a claim."""
    assert EnrolmentFact("C", "assigned", done=0, total=0).percent is None
    assert EnrolmentFact("C", "assigned").percent is None


def test_a_past_deadline_is_overdue_until_it_is_completed() -> None:
    late = EnrolmentFact("C", "in_progress", deadline=date(2026, 7, 1))
    done = EnrolmentFact("C", "completed", deadline=date(2026, 7, 1))

    assert late.is_overdue(TODAY) is True
    assert done.is_overdue(TODAY) is False


def test_needs_attention_is_overdue_or_never_opened() -> None:
    assert EnrolmentFact("C", "assigned").needs_attention(TODAY) is True
    assert EnrolmentFact("C", "in_progress").needs_attention(TODAY) is False
    assert (
        EnrolmentFact("C", "in_progress", deadline=date(2020, 1, 1)).needs_attention(TODAY)
        is True
    )


# -- the privacy allowlist ----------------------------------------------------------
def _attributes_read_by(module) -> set[str]:
    """Every ``x.attr`` the module's code touches. Docstrings and prose are not nodes."""
    tree = ast.parse(inspect.getsource(module))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_PROFILE_FIELDS))
def test_the_snapshot_never_reads_a_private_profile_column(forbidden: str) -> None:
    """``preset``, ``format_vector``, ``accessibility`` and friends are the employee's.

    They are how a person asked to be taught — including reading needs — and naming an
    individual with them is the disclosure this product's RGPD position rules out (§6).
    An attribute access is how they would be selected, so an attribute access is what is
    forbidden; the docstrings above are free to name them, and do.
    """
    assert forbidden not in _attributes_read_by(snapshot_module)


def test_the_only_profile_column_that_travels_is_the_job_title() -> None:
    source = inspect.getsource(snapshot_module)
    accesses = {
        line.strip()
        for line in source.splitlines()
        if "LearnerProfile." in line and not line.strip().startswith("#")
    }
    referenced = {
        access.split("LearnerProfile.")[1].split()[0].strip(",.)")
        for access in accesses
    }
    assert referenced <= {"role_title", "user_id", "org_id"}


def test_the_rendered_block_carries_no_private_value() -> None:
    """Belt and braces: the text itself, not just the queries behind it."""
    text = render_snapshot(_snapshot(employees=(LUCIA, MARCOS))).lower()
    for forbidden in ("format_vector", "tutor_notes", "accessibility", "short_blocks"):
        assert forbidden not in text


def test_the_employee_fact_has_no_field_for_a_private_signal() -> None:
    """The shape is the guarantee: there is nowhere to put one, so none can leak."""
    assert set(EmployeeFact.__dataclass_fields__) == {
        "full_name",
        "role_title",
        "active",
        "hired_on",
        "enrolments",
        "skills",
        "nodes_mastered",
    }


# -- the summary the model is forbidden to compute ------------------------------------
def test_the_totals_are_counted_here_so_the_model_never_adds() -> None:
    """Without a headline to quote, a small model answers with five name-by-name blocks."""
    text = render_snapshot(_snapshot(employees=(LUCIA, MARCOS)))

    assert "RESUMEN (ya contado, no lo recalcules)" in text
    assert "- empleados: 2" in text
    assert "asignaciones de curso: 3 (1 completadas, 1 en curso, 1 sin empezar)" in text


def test_the_summary_names_who_is_late_and_who_never_started() -> None:
    idle = EmployeeFact(
        full_name="Noa Pereira Ramos",
        enrolments=(EnrolmentFact("Alergenos", "assigned", 0, 5, "nodos"),),
    )
    text = render_snapshot(_snapshot(employees=(LUCIA, MARCOS, idle)))

    assert "no han empezado NINGUNO de sus cursos: 1 (Noa Pereira Ramos)" in text
    assert "algun plazo vencido: 1 (Lucia Fernandez Vila)" in text
    assert "sin ningun curso asignado: 0" in text


def test_someone_with_no_courses_is_counted_separately_from_someone_who_stalled() -> None:
    """"No ha empezado" and "no tiene nada asignado" are different problems."""
    text = render_snapshot(
        _snapshot(employees=(EmployeeFact(full_name="Sin Cursos Ninguno"),))
    )
    assert "sin ningun curso asignado: 1 (Sin Cursos Ninguno)" in text
    assert "no han empezado NINGUNO de sus cursos: 0" in text


def test_a_long_name_list_is_cut_but_its_count_never_is() -> None:
    """A truncated list next to a truncated count would be two lies for the price of one."""
    stalled = tuple(
        EmployeeFact(
            full_name=f"Persona {i:02d}",
            enrolments=(EnrolmentFact("C", "assigned"),),
        )
        for i in range(14)
    )
    text = render_snapshot(_snapshot(employees=stalled))

    assert "no han empezado NINGUNO de sus cursos: 14 (" in text
    assert "+4 mas)" in text


# -- the rendering ------------------------------------------------------------------
def test_an_empty_organization_renders_to_nothing() -> None:
    """No employees, no courses, no documents: no block, and the turn is unchanged."""
    assert render_snapshot(_snapshot()) == ""


def test_every_number_is_printed_so_nothing_has_to_be_computed() -> None:
    text = render_snapshot(_snapshot(employees=(LUCIA,)))

    assert "Lucia Fernandez Vila (Dependiente)" in text
    assert "40% (2/5 nodos)" in text
    assert "0% (0/4 lecciones)" in text


def test_an_overdue_deadline_is_shouted_not_left_to_be_worked_out() -> None:
    text = render_snapshot(_snapshot(employees=(LUCIA,)))

    assert "plazo 2026-07-01 (FUERA DE PLAZO)" in text
    assert "plazo 2026-08-15 (FUERA DE PLAZO)" not in text


def test_a_person_with_no_courses_says_so_rather_than_being_a_blank_line() -> None:
    text = render_snapshot(
        _snapshot(employees=(EmployeeFact(full_name="Noa Pereira Ramos"),))
    )
    assert "- Noa Pereira Ramos" in text
    assert "sin cursos asignados" in text


def test_skills_are_rendered_in_spanish_levels() -> None:
    text = render_snapshot(_snapshot(employees=(LUCIA,)))
    assert "caja_tpv (medio)" in text
    assert "gestion_alergenos (bajo)" in text


def test_courses_carry_their_state_and_their_assignment_counts() -> None:
    text = render_snapshot(
        _snapshot(
            courses=(
                CourseFact(
                    title="Alergenos e informacion al cliente",
                    status="publicado",
                    delivery="dinamico",
                    units=5,
                    unit_name="nodos",
                    assigned=1,
                    in_progress=2,
                    completed=2,
                ),
            )
        )
    )
    assert "publicado (dinamico), 5 nodos" in text
    assert "5 asignaciones (2 completadas, 2 en curso, 1 sin empezar)" in text


def test_a_static_course_does_not_say_static_on_every_line() -> None:
    """On a v1 deployment every course is static, so the word distinguishes nothing."""
    text = render_snapshot(
        _snapshot(
            courses=(
                CourseFact("Manejo de caja", "publicado", "estatico", 4, "lecciones"),
            )
        )
    )
    assert "- Manejo de caja: publicado, 4 lecciones" in text
    assert "estatico" not in text


@pytest.mark.parametrize(
    ("delivery_mode", "lessons", "nodes", "expected"),
    [
        # Served dynamically: measured in nodes, which is what the learner advances in.
        ("dynamic", 0, 5, ("nodos", "dinamico", 5)),
        ("dynamic", 3, 5, ("nodos", "dinamico", 5)),
        ("static", 4, 0, ("lecciones", "estatico", 4)),
        # Nothing to count at all: no unit, rather than a "0 lecciones" that reads false.
        ("static", 0, 0, ("", "estatico", 0)),
    ],
)
def test_a_course_is_counted_in_the_unit_it_actually_has(
    delivery_mode, lessons, nodes, expected
) -> None:
    """A schema-first course has nodes and no lessons; "0 lecciones" would read as empty."""
    course = SimpleNamespace(delivery_mode=delivery_mode, schema_status="validated")

    assert snapshot_module._units_for(course, lessons=lessons, nodes=nodes) == expected


def test_documents_are_titles_only() -> None:
    text = render_snapshot(
        _snapshot(documents=("Manual de alergenos",), documents_total=1)
    )
    assert "DOCUMENTOS SUBIDOS (1)" in text
    assert "- Manual de alergenos" in text


def test_a_trimmed_list_says_it_is_trimmed_and_keeps_the_urgent_people() -> None:
    """A truncated list that silently drops the overdue person reads like an all-clear."""
    calm = tuple(
        EmployeeFact(
            full_name=f"Empleado Tranquilo {i:02d}",
            enrolments=(EnrolmentFact("C", "in_progress", done=1, total=2),),
        )
        for i in range(MAX_EMPLOYEES_LISTED + 5)
    )
    urgent = EmployeeFact(
        full_name="Zulema Ultima Alfabeticamente",
        enrolments=(EnrolmentFact("C", "in_progress", deadline=date(2020, 1, 1)),),
    )
    text = render_snapshot(_snapshot(employees=(*calm, urgent)))

    assert f"EMPLEADOS ({MAX_EMPLOYEES_LISTED + 6})" in text
    assert f"se listan {MAX_EMPLOYEES_LISTED} de {MAX_EMPLOYEES_LISTED + 6}" in text
    assert "La lista es PARCIAL" in text
    assert "Zulema Ultima Alfabeticamente" in text


def test_a_small_organization_is_never_trimmed_and_never_says_it_was() -> None:
    text = render_snapshot(_snapshot(employees=(LUCIA, MARCOS)))
    assert "PARCIAL" not in text
    assert "EMPLEADOS (2)" in text


def test_the_seeded_organization_stays_small_enough_to_paste_every_turn() -> None:
    """Five employees, three courses: the whole argument against tool-calling, measured."""
    text = render_snapshot(
        _snapshot(
            employees=tuple(
                EmployeeFact(
                    full_name=f"Empleado Numero {i}",
                    role_title="Camarero",
                    hired_on=date(2024, 1, 1),
                    enrolments=(
                        EnrolmentFact("Alergenos", "in_progress", 2, 5, "nodos"),
                        EnrolmentFact("Sala", "assigned", 0, 4, "nodos"),
                        EnrolmentFact("Caja", "completed", 6, 6, "lecciones"),
                    ),
                    skills=(("atencion_cliente", "medium"),),
                    nodes_mastered=2,
                )
                for i in range(5)
            ),
            courses=(
                CourseFact("Alergenos", "publicado", "dinamico", 5, "nodos", 1, 3, 1),
                CourseFact("Sala", "publicado", "dinamico", 4, "nodos", 4, 0, 0),
                CourseFact("Caja", "publicado", "estatico", 6, "lecciones", 0, 0, 4),
            ),
            documents=("Manual de alergenos", "Protocolo de sala", "Manejo de caja"),
            documents_total=3,
        )
    )
    # ~1.5 kB, i.e. well under 500 tokens: cheaper than a single tool round trip.
    assert len(text) < 2_500
