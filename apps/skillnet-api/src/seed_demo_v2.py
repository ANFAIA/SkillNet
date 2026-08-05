"""Seed a realistic v2 (dynamic courses) demo dataset — something to actually play with.

Run from inside the API container::

    docker compose exec api python -m src.seed_demo_v2

Or from the host, with the API's ``.env`` loaded::

    uv run python -m src.seed_demo_v2

What it creates (all of it inside the single organization the app bootstraps):

* A credible Spanish SME: a bakery-café with a small dining room, ``sector='hosteleria'``
  so the onboarding role suggestions match.
* Five employees with different jobs, different declared experience and different presets.
  **Four of them already have a populated ``learner_profiles`` row**, so the personalisation
  is visible without filling five onboarding wizards by hand; the fifth deliberately has
  none, which is the one to walk the wizard with.
* Three source documents with real prose. All of them are <= 5 pages, which is the
  ``full_text`` branch of ``load_source_context`` (§4.2): the *node runtime* reads the
  whole document and needs no embeddings. They are **also chunked and embedded** (best
  effort, see ``_ensure_chunks``), because the tutor chat is RAG over ``document_chunks``
  and a demo whose chunk table is empty never exercises that half of the product. If no
  embedding provider is configured the chunks are skipped with a warning and the tutor
  still answers — from ``full_text``, which is rung 2 of the ladder in
  ``src/services/retrieval.py``.
* Two **dynamic** courses whose schema is already ``validated``: a 3-node compliance one
  and a 7-node process one. Every node carries its pre-generated ``probe_items`` /
  ``probe_answer_key`` (§7.1 origin 1), so opening a node costs zero probe tokens.
* One **static v1** course, untouched by v2, to compare the two paths side by side.

Two properties this module is written to keep:

1. **It is idempotent.** Every row is get-or-created by a natural key (email, title,
   position), so running it twice changes nothing. It never rewrites a node that already
   exists — see ``--refresh`` for the deliberate exception.
2. **It validates itself with production code.** The schema graphs go through
   ``validate_schema_graph`` and every probe through ``validate_probe_items`` before the
   transaction commits. If the data below ever stops satisfying the gate of §11.1, the
   seed fails loudly here instead of producing a demo that 422s in the browser.

``--refresh`` is the quality loop: edit the specs in this file, re-run with ``--refresh``
and the *design-time* fields of the existing nodes (title, summary, outcome, criticality,
headings, probe, format, minutes) are overwritten in place, ``courses.schema_version`` is
bumped — which is part of the ``cache_key``, so cached renders are invalidated — and the
per-learner render pins are cleared so the next visit regenerates. Learner progress is
kept.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

from src.config import settings
from src.core.logging import configure_logging, get_logger
from src.deps.db import async_session_factory, engine
from src.models import (
    ContentStatus,
    Course,
    CourseDeliveryMode,
    CourseNode,
    CourseNodePrerequisite,
    CourseSchemaStatus,
    CourseSkill,
    Document,
    DocumentStatus,
    Enrollment,
    Exercise,
    ExerciseType,
    LearnerNodeState,
    Lesson,
    Module,
    NodeCriticality,
    Organization,
    Skill,
    SkillCategory,
    SkillLevel,
    UiFormat,
    User,
    UserRole,
    UserSkill,
)
from src.llm.embedding import resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder
from src.repositories.document_chunk_repo import DocumentChunkRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.seed_demo import TAXONOMY
from src.services.chunker import chunk_sections
from src.services.course_schema_service import (
    default_threshold_for,
    validate_schema_graph,
)
from src.services.document_parser import ParsedSection
from src.services.learner_profile_service import LearnerProfileService
from src.services.probe_service import validate_probe_items

configure_logging("INFO")
logger = get_logger(__name__)

# --------------------------------------------------------------------------------------
# The company
# --------------------------------------------------------------------------------------
DEMO_ORG_NAME = "Panaderia y Cafeteria La Espiga S.L."
DEMO_SECTOR = "hosteleria"
#: Only an organization still carrying a placeholder name gets renamed (see ``_ensure_org``).
PLACEHOLDER_ORG_NAMES = frozenset({"SkillNet", "Your Company", "Tu empresa"})

DEMO_PASSWORD = "espiga2026"
EMAIL_DOMAIN = "laespiga.example"  # RFC 2606 reserved TLD: never routable


# --------------------------------------------------------------------------------------
# Specs — plain data, importable by the tests without a database
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class EmployeeSpec:
    """One demo employee, and the learner profile they arrive with."""

    email_local: str
    full_name: str
    job: str  # what the owner sees in the summary; not stored as such
    role_title: str  # learner_profiles.role_title — this DOES travel to the LLM
    hired_at: date
    skills: dict[str, SkillLevel]
    #: ``None`` means "no learner_profiles row at all": the account to test onboarding with.
    goal: str | None = None
    experience: str | None = None
    preset: str = "standard"
    accessibility: dict[str, bool] = field(default_factory=dict)
    #: >= 3 takes the learner out of the calibration period of §6.4, so ``decide_formato``
    #: actually runs for them. Set on exactly one employee, on purpose.
    nodes_completed: int = 0
    format_vector: dict[str, float] | None = None
    note: str = ""

    @property
    def email(self) -> str:
        return f"{self.email_local}@{EMAIL_DOMAIN}"

    @property
    def has_profile(self) -> bool:
        return self.experience is not None


EMPLOYEES: tuple[EmployeeSpec, ...] = (
    EmployeeSpec(
        email_local="lucia.fernandez",
        full_name="Lucia Fernandez Vila",
        job="Dependienta de tienda y obrador",
        role_title="Dependiente",
        hired_at=date(2023, 9, 4),
        skills={
            "caja_tpv": SkillLevel.MEDIUM,
            "atencion_cliente": SkillLevel.MEDIUM,
            "manipulacion_alimentos": SkillLevel.LOW,
            "gestion_alergenos": SkillLevel.LOW,
        },
        goal="specific_gap",
        experience="some",
        preset="standard",
        note="Perfil medio. El caso normal contra el que comparar todo lo demas.",
    ),
    EmployeeSpec(
        email_local="marcos.iglesias",
        full_name="Marcos Iglesias Rey",
        job="Cocinero",
        role_title="Cocinero",
        hired_at=date(2019, 3, 18),
        skills={
            "preparacion_platos": SkillLevel.HIGH,
            "control_temperaturas": SkillLevel.HIGH,
            "manipulacion_alimentos": SkillLevel.HIGH,
            "gestion_alergenos": SkillLevel.MEDIUM,
        },
        goal="assigned",
        experience="experienced",
        preset="fast",
        note="Experto declarado + preset rapido: los pre-assessments deberian saltarle nodos.",
    ),
    EmployeeSpec(
        email_local="aitana.souto",
        full_name="Aitana Souto Blanco",
        job="Camarera de sala (recien incorporada)",
        role_title="Camarero",
        hired_at=date(2026, 6, 1),
        skills={"atencion_cliente": SkillLevel.LOW},
        goal="onboarding",
        experience="none",
        preset="focus",
        accessibility={
            "short_blocks": True,
            "reduce_motion": False,
            "high_contrast": False,
            "extra_time": True,
        },
        note=(
            "Novata declarada: su primer probe es diagnostico (no puntua) y 'short_blocks' "
            "recorta la densidad del prompt a 2."
        ),
    ),
    EmployeeSpec(
        email_local="diego.varela",
        full_name="Diego Varela Nunez",
        job="Encargado de sala",
        role_title="Encargado de sala",
        hired_at=date(2017, 11, 2),
        skills={
            "gestion_turnos": SkillLevel.HIGH,
            "apertura_cierre": SkillLevel.HIGH,
            "caja_tpv": SkillLevel.HIGH,
            "control_costes": SkillLevel.MEDIUM,
            "formacion_equipo": SkillLevel.MEDIUM,
        },
        goal="specific_gap",
        experience="experienced",
        preset="standard",
        nodes_completed=4,
        format_vector={"texto": 0.45, "ejercicio": 0.35, "codigo": 0.0, "dato": 0.20},
        note=(
            "Fuera del periodo de calibracion (nodes_completed=4): en sus nodos SI corre "
            "decide_formato y el router de dos niveles."
        ),
    ),
    EmployeeSpec(
        email_local="noa.pereira",
        full_name="Noa Pereira Ramos",
        job="Camarera de fin de semana",
        role_title="Camarero",
        hired_at=date(2025, 4, 12),
        skills={"atencion_cliente": SkillLevel.LOW},
        note="SIN perfil de aprendiz a proposito: es la cuenta para recorrer el onboarding.",
    ),
)


@dataclass(frozen=True)
class DocumentSpec:
    key: str
    title: str
    filename: str
    page_count: int
    sections: tuple[tuple[str, str], ...]

    @property
    def headings(self) -> tuple[str, ...]:
        return tuple(heading for heading, _ in self.sections)

    @property
    def full_text(self) -> str:
        blocks = [self.title, ""]
        for heading, body in self.sections:
            blocks.extend([heading, "", body, ""])
        return "\n".join(blocks).strip() + "\n"


DOC_ALERGENOS = DocumentSpec(
    key="alergenos",
    title="Manual de alergenos e informacion al cliente",
    filename="manual-alergenos.md",
    page_count=3,
    sections=(
        (
            "Marco legal",
            "El Reglamento (UE) 1169/2011 y el Real Decreto 126/2015 obligan a informar de "
            "la presencia de los catorce alergenos de declaracion obligatoria en cualquier "
            "alimento que se sirva sin envasar. La informacion debe estar disponible por "
            "escrito y ser accesible al cliente antes de que pida. La responsabilidad de "
            "que esa informacion sea correcta es del establecimiento, nunca del cliente.",
        ),
        (
            "Los catorce alergenos de declaracion obligatoria",
            "Cereales con gluten (trigo, centeno, cebada, avena, espelta, kamut). "
            "Crustaceos. Huevos. Pescado. Cacahuetes. Soja. Leche, incluida la lactosa. "
            "Frutos de cascara (almendra, avellana, nuez, anacardo, pistacho y similares). "
            "Apio. Mostaza. Granos de sesamo. Dioxido de azufre y sulfitos en "
            "concentraciones superiores a 10 mg/kg. Altramuces. Moluscos. "
            "En La Espiga, la masa madre, las empanadas y toda la bolleria llevan cereales "
            "con gluten; el hojaldre y las cremas llevan ademas leche y huevo.",
        ),
        (
            "Como se informa al cliente",
            "Cada producto del obrador tiene una ficha con su lista de ingredientes y sus "
            "alergenos, archivada en la carpeta roja del mostrador y en el TPV. Ante una "
            "pregunta de un cliente nunca se responde de memoria: se consulta la ficha del "
            "producto y se lee lo que pone. Si la ficha no esta, o si el producto se ha "
            "elaborado fuera de la pauta habitual, se dice con claridad que no se puede "
            "garantizar y se ofrece una alternativa cuya ficha si este disponible. "
            "La frase 'creo que no lleva' esta prohibida.",
        ),
        (
            "Contaminacion cruzada en el obrador",
            "La harina de trigo permanece en suspension en el aire hasta veinte minutos "
            "despues de amasar, asi que un pedido sin gluten no se prepara justo despues de "
            "un amasado. Antes de elaborar sin gluten se limpian a fondo superficie, "
            "amasadora y utensilios, se cambian los guantes y se usa tabla y cuchillo "
            "propios, identificados en verde. La freidora es compartida: cualquier producto "
            "frito puede contener trazas de gluten y asi se declara. El orden de elaboracion "
            "del turno empieza siempre por lo sin gluten y termina por lo demas.",
        ),
        (
            "Que hacer ante una reaccion alergica",
            "Si un cliente presenta hinchazon, dificultad para respirar o erupcion despues "
            "de consumir un producto: se avisa de inmediato al encargado, no se mueve al "
            "cliente, se llama al 112 y se le acompana. Se conserva el resto del producto y "
            "el ticket para poder trazar el lote. Antes de terminar el turno se registra la "
            "incidencia en el parte, con hora, producto y lote.",
        ),
    ),
)

DOC_SALA = DocumentSpec(
    key="sala",
    title="Protocolo de sala: de la comanda al cobro",
    filename="protocolo-sala.md",
    page_count=4,
    sections=(
        (
            "Apertura del turno",
            "Quince minutos antes de abrir: revisar las reservas del dia, comprobar el "
            "montaje de las mesas, encender el TPV y contar el fondo de caja, que es de "
            "150 euros en cambio. Si el fondo no cuadra se completa y se registra la "
            "diferencia antes de abrir, nunca al cierre. Se comprueba la carta del dia y las "
            "roturas de stock con cocina y se cierra con un briefing de cinco minutos en el "
            "que todo el turno sabe que hay, que falta y cuantas reservas entran.",
        ),
        (
            "Recepcion y acomodo del cliente",
            "Todo cliente que entra recibe un saludo en menos de treinta segundos, aunque "
            "estemos ocupados: si no se le puede atender, se le dice que ahora mismo estamos "
            "con el. Se pregunta si tiene reserva y cuantos son, se le acompana a la mesa y "
            "se le entrega la carta. En el momento de entregar la carta se ofrece la "
            "informacion de alergenos y se sirve el agua.",
        ),
        (
            "Toma de comanda en el TPV",
            "La comanda se toma siguiendo un orden fijo de la mesa, en sentido horario "
            "empezando por la persona sentada a la izquierda de quien mira desde la puerta; "
            "asi se sirve despues sin preguntar de quien es cada plato. Cada alergeno "
            "declarado por un comensal se marca en la linea del plato en el TPV, ademas de "
            "avisarlo de viva voz al pase. Se pregunta el punto de las carnes. Antes de "
            "enviar, se repite la comanda en voz alta al cliente para detectar errores antes "
            "de que lleguen a cocina. Los envios se hacen por rondas: primeros y segundos "
            "nunca van en el mismo disparo.",
        ),
        (
            "Coordinacion con cocina y tiempos",
            "El pase manda: cuando el pase canta una mesa, esa mesa se recoge de inmediato. "
            "El tiempo objetivo de salida es de doce minutos para los primeros y dieciocho "
            "para los segundos, contando desde el envio. Si cocina se retrasa mas de cinco "
            "minutos sobre el objetivo, se avisa a la mesa antes de que pregunte y se le da "
            "un tiempo concreto. Cuando entran dos mesas grandes a la vez se avisa al pase "
            "antes de enviar la segunda.",
        ),
        (
            "Servicio en mesa y seguimiento",
            "Se sirve por la derecha y se retira por la derecha. No se retira ningun plato "
            "hasta que han terminado todos los comensales de la mesa. A los tres minutos del "
            "primer bocado se hace el repaso: se pregunta si todo esta correcto y se rellena "
            "el agua. Tras retirar los segundos se ofrecen postres y cafes, en ese orden, "
            "antes de que el cliente pida la cuenta.",
        ),
        (
            "Cobro y cierre de mesa",
            "La cuenta se pide en el TPV por numero de mesa y se comprueba contra lo servido "
            "antes de llevarla. El cobro se hace en la mesa con el datafono, que no se deja "
            "nunca sin vigilancia. Siempre se entrega el ticket, aunque el cliente no lo "
            "pida. Despues de cobrar se cierra la mesa en el TPV: hasta que no se cierra, la "
            "mesa sigue ocupada en el sistema y el arqueo del turno no cuadra.",
        ),
        (
            "Incidencias y quejas",
            "Ante una queja se escucha sin interrumpir, se pide disculpas y se ofrece una "
            "solucion en menos de dos minutos. No se justifica nunca con 'es la politica de "
            "la casa' ni se echa la culpa a cocina delante del cliente. Si la compensacion "
            "supera los veinte euros, o si hay cualquier riesgo para la salud, se avisa al "
            "encargado antes de comprometer nada. Toda incidencia se anota en el parte de "
            "turno para que el turno siguiente la conozca.",
        ),
        (
            "Cierre del turno",
            "Al cerrar se hace el arqueo: se cuenta el efectivo, se imprime el desglose por "
            "medio de pago del TPV y se comparan. La diferencia maxima tolerada es de cinco "
            "euros; por encima de eso se avisa al encargado y no se cierra la caja sin el. "
            "Se deja el fondo de 150 euros para el turno siguiente y se firma el parte de "
            "incidencias.",
        ),
    ),
)

DOC_CAJA = DocumentSpec(
    key="caja",
    title="Manejo de caja y arqueo diario",
    filename="manejo-de-caja.md",
    page_count=2,
    sections=(
        (
            "Fondo de caja",
            "El fondo de caja es de 150 euros en cambio: monedas y billetes pequenos. Se "
            "cuenta al abrir y al cerrar, siempre por la misma persona que firma el parte.",
        ),
        (
            "Cobros y medios de pago",
            "Se admite efectivo, tarjeta y pago movil. El ticket se entrega siempre. Los "
            "vales de comida se registran como medio de pago propio, no como descuento.",
        ),
        (
            "Arqueo de cierre",
            "El arqueo compara el efectivo contado con el desglose del TPV. Se hace con la "
            "caja cerrada al publico y sin interrupciones.",
        ),
        (
            "Descuadres",
            "Una diferencia de hasta cinco euros se anota y se cierra. Por encima de cinco "
            "euros se avisa al encargado y se revisan los tickets del turno uno a uno.",
        ),
    ),
)

DOCUMENTS: tuple[DocumentSpec, ...] = (DOC_ALERGENOS, DOC_SALA, DOC_CAJA)


# --------------------------------------------------------------------------------------
# Probe items (§7.1). Pre-generated here, so opening a node costs zero probe tokens.
# --------------------------------------------------------------------------------------
def probe(
    *,
    question_a: str,
    options_a: tuple[str, str, str, str],
    correct_a: int,
    explain_a: str,
    question_b: str,
    options_b: tuple[str, str, str, str],
    correct_b: int,
    explain_b: str,
    template_c: str | None = None,
    answer_c: str | None = None,
    explain_c: str | None = None,
) -> tuple[list[dict], dict]:
    """Build ``(probe_items, probe_answer_key)`` for one node.

    Slot ``a`` is the deciding item and therefore carries Bloom ``apply``; ``b`` checks
    comprehension (``understand``). Slot ``c`` is the constructed tie-break: **mandatory on
    a ``critical`` node** and optional elsewhere, where it only appears once the verdict
    lands in the doubt band. It is a ``fill_blank`` with exactly **one** blank, because that
    is what ``ProbeRunner`` submits (``{"answers": [text]}``).

    The statement lives in the item and the solution in the key: that separation is the
    structural reason the answer cannot leak (``src/services/node_grading.py``).
    """
    items: list[dict] = [
        {
            "item_id": "a",
            "item_type": "test",
            "bloom_level": "apply",
            "question": question_a,
            "options": list(options_a),
        },
        {
            "item_id": "b",
            "item_type": "test",
            "bloom_level": "understand",
            "question": question_b,
            "options": list(options_b),
        },
    ]
    answer_key: dict[str, dict] = {
        "a": {"correct": correct_a, "explanation": explain_a},
        "b": {"correct": correct_b, "explanation": explain_b},
    }
    if template_c is not None and answer_c is not None:
        items.append(
            {
                "item_id": "c",
                "item_type": "fill_blank",
                "bloom_level": "apply",
                "template": template_c,
            }
        )
        answer_key["c"] = {"blanks": [answer_c], "explanation": explain_c or ""}
    return items, answer_key


@dataclass(frozen=True)
class NodeSpec:
    key: str
    title: str
    summary: str
    outcome: str
    criticality: NodeCriticality
    position: int
    headings: tuple[str, ...]
    ui_format: UiFormat
    estimated_minutes: int
    probe_items: list[dict]
    probe_answer_key: dict
    prerequisites: tuple[str, ...] = ()
    skill: str | None = None
    #: Title of the v1 backup lesson to attach as ``seed_lesson_id`` (degraded mode, §4.2).
    seed_lesson: str | None = None


@dataclass(frozen=True)
class DynamicCourseSpec:
    title: str
    description: str
    outcome: str
    document_key: str
    intent_density: int
    nodes: tuple[NodeSpec, ...]
    #: v1 lessons created alongside, only to be used as the degraded-mode fallback.
    backup_module: str | None = None
    backup_lessons: tuple[tuple[str, str], ...] = ()


# ---------------------------------------------------------------- compliance (3 nodes) --
_ALERGENOS_NODES: tuple[NodeSpec, ...] = (
    NodeSpec(
        key="catorce",
        title="Los catorce alergenos obligatorios",
        summary=(
            "Que alergenos hay que declarar por ley y cuales aparecen en los productos que "
            "salen del obrador de La Espiga todos los dias."
        ),
        outcome="Identificar sin dudar los alergenos presentes en los productos de la casa.",
        criticality=NodeCriticality.CRITICAL,
        position=1,
        headings=("Los catorce alergenos de declaracion obligatoria", "Marco legal"),
        ui_format=UiFormat.EXPLANATION,
        estimated_minutes=8,
        skill="gestion_alergenos",
        seed_lesson="Los catorce alergenos, en corto",
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Un cliente pregunta que alergenos lleva la empanada de atun de la "
                        "casa. Ademas del pescado, cual esta siempre presente?"
                    ),
                    options_a=(
                        "Cereales con gluten, por la masa",
                        "Altramuces",
                        "Moluscos",
                        "Apio",
                    ),
                    correct_a=0,
                    explain_a=(
                        "Toda la masa del obrador lleva harina de trigo, asi que cereales "
                        "con gluten esta siempre."
                    ),
                    question_b=(
                        "Cuantos alergenos son de declaracion obligatoria en la Union "
                        "Europea?"
                    ),
                    options_b=("Siete", "Diez", "Catorce", "Veinte"),
                    correct_b=2,
                    explain_b="Son catorce, fijados por el Reglamento (UE) 1169/2011.",
                    template_c=(
                        "El reglamento europeo que fija la informacion obligatoria sobre "
                        "alergenos al consumidor es el Reglamento (UE) ___/2011."
                    ),
                    answer_c="1169",
                    explain_c="Reglamento (UE) 1169/2011.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="informar",
        title="Responder a la pregunta de un cliente",
        summary=(
            "Que se contesta, y que no se contesta nunca, cuando un cliente pregunta si un "
            "producto lleva un alergeno concreto."
        ),
        outcome=(
            "Resolver una consulta de alergenos consultando la ficha, sin improvisar y sin "
            "dejar al cliente sin alternativa."
        ),
        criticality=NodeCriticality.CRITICAL,
        position=2,
        headings=("Como se informa al cliente",),
        ui_format=UiFormat.EXERCISE,
        estimated_minutes=10,
        skill="atencion_cliente",
        prerequisites=("catorce",),
        seed_lesson="Como se responde a una consulta de alergenos",
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Una clienta celiaca pregunta si el bizcocho de zanahoria lleva "
                        "gluten y la ficha del producto no esta en la carpeta. Que haces?"
                    ),
                    options_a=(
                        "Le dices que crees que no lleva, porque no ves harina en la receta",
                        "Le dices que no puedes garantizarlo y le ofreces un producto cuya "
                        "ficha si este disponible",
                        "Le preguntas si es muy alergica y decides segun lo que conteste",
                        "Se lo sirves avisandole de que vaya con cuidado",
                    ),
                    correct_a=1,
                    explain_a=(
                        "Sin ficha no hay garantia. Se dice con claridad y se ofrece "
                        "alternativa: 'creo que no lleva' esta prohibido."
                    ),
                    question_b=(
                        "Por que la informacion de alergenos tiene que estar disponible "
                        "antes de que el cliente pida?"
                    ),
                    options_b=(
                        "Para agilizar el servicio",
                        "Porque el cliente decide con la informacion delante y la "
                        "responsabilidad es del establecimiento",
                        "Porque lo exige el proveedor de harina",
                        "Porque si no, no se puede cobrar el producto",
                    ),
                    correct_b=1,
                    explain_b=(
                        "La ley pone la responsabilidad en el establecimiento y exige que la "
                        "informacion sea accesible antes de la compra."
                    ),
                    template_c=(
                        "Ante una duda sobre alergenos la respuesta no se da de memoria: se "
                        "consulta la ___ del producto."
                    ),
                    answer_c="ficha",
                    explain_c="La ficha de producto, en la carpeta roja y en el TPV.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="cruzada",
        title="Evitar la contaminacion cruzada en el obrador",
        summary=(
            "Como se prepara un pedido sin gluten en un obrador donde se amasa con harina de "
            "trigo todos los dias."
        ),
        outcome="Preparar un pedido sin gluten sin arrastrar trazas del resto del obrador.",
        criticality=NodeCriticality.RECOMMENDED,
        position=3,
        headings=("Contaminacion cruzada en el obrador",),
        ui_format=UiFormat.EXPLANATION,
        estimated_minutes=7,
        skill="manipulacion_alimentos",
        prerequisites=("catorce",),
        seed_lesson="Contaminacion cruzada: lo minimo",
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Acabas de amasar pan de trigo y entra un pedido sin gluten. Cual es "
                        "el primer paso?"
                    ),
                    options_a=(
                        "Cambiar de guantes y seguir en la misma mesa",
                        "Pasar un pano por la mesa y continuar",
                        "Limpiar a fondo superficie y utensilios y esperar a que no quede "
                        "harina en suspension",
                        "Prepararlo en la freidora, que esta libre",
                    ),
                    correct_a=2,
                    explain_a=(
                        "La harina sigue en el aire hasta veinte minutos: limpieza a fondo y "
                        "espera, no solo guantes."
                    ),
                    question_b="Que es la contaminacion cruzada?",
                    options_b=(
                        "Que un producto caduque antes de tiempo",
                        "Que un alergeno pase a un alimento que no lo lleva, por el aire, "
                        "las manos o los utensilios",
                        "Que dos pedidos se confundan al servirlos",
                        "Que la camara este a mas temperatura de la debida",
                    ),
                    correct_b=1,
                    explain_b=(
                        "Es el paso involuntario de un alergeno a un alimento que no lo "
                        "contiene."
                    ),
                    template_c=(
                        "En el obrador, la tabla y el cuchillo reservados para lo sin gluten "
                        "se identifican con el color ___."
                    ),
                    answer_c="verde",
                    explain_c="Verde, segun la pauta del obrador.",
                ),
                strict=True,
            )
        ),
    ),
)

COURSE_ALERGENOS = DynamicCourseSpec(
    title="Alergenos: informar sin equivocarse",
    description=(
        "Curso de cumplimiento, corto y obligatorio para todo el personal que atiende "
        "publico o manipula alimentos."
    ),
    outcome=(
        "Responder correctamente a cualquier consulta de alergenos y preparar un pedido sin "
        "gluten sin contaminarlo."
    ),
    document_key="alergenos",
    intent_density=2,
    nodes=_ALERGENOS_NODES,
    backup_module="Contenido de respaldo (v1)",
    backup_lessons=(
        (
            "Los catorce alergenos, en corto",
            "## Los catorce alergenos\n\n"
            "Cereales con gluten, crustaceos, huevos, pescado, cacahuetes, soja, leche, "
            "frutos de cascara, apio, mostaza, sesamo, sulfitos (>10 mg/kg), altramuces y "
            "moluscos.\n\n"
            "En La Espiga: toda la masa lleva **gluten**; el hojaldre y las cremas llevan "
            "ademas **leche** y **huevo**.\n",
        ),
        (
            "Como se responde a una consulta de alergenos",
            "## La regla\n\n"
            "1. No se responde de memoria.\n"
            "2. Se consulta la ficha del producto (carpeta roja o TPV) y se lee.\n"
            "3. Si no hay ficha o hay duda: se dice que no se puede garantizar y se ofrece "
            "una alternativa con ficha.\n\n"
            "La frase *\"creo que no lleva\"* esta prohibida.\n",
        ),
        (
            "Contaminacion cruzada: lo minimo",
            "## Antes de elaborar sin gluten\n\n"
            "- Limpieza a fondo de superficie, amasadora y utensilios.\n"
            "- Guantes nuevos, tabla y cuchillo verdes.\n"
            "- Nunca justo despues de amasar: la harina esta en el aire hasta 20 minutos.\n"
            "- La freidora es compartida: todo lo frito se declara con trazas.\n",
        ),
    ),
)

# ------------------------------------------------------------------- process (7 nodes) --
_SALA_NODES: tuple[NodeSpec, ...] = (
    NodeSpec(
        key="apertura",
        title="Apertura del turno de sala",
        summary=(
            "Lo que hay que dejar comprobado en los quince minutos previos a abrir: "
            "reservas, montaje, fondo de caja y briefing."
        ),
        outcome="Abrir el turno con la caja cuadrada y el equipo sabiendo que hay y que falta.",
        criticality=NodeCriticality.RECOMMENDED,
        position=1,
        headings=("Apertura del turno",),
        ui_format=UiFormat.EXPLANATION,
        estimated_minutes=6,
        skill="apertura_cierre",
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Abres el turno y en el cajon hay 90 euros. El fondo de caja fijado "
                        "es de 150. Que haces antes de abrir?"
                    ),
                    options_a=(
                        "Abrir igual y anotarlo en el arqueo del cierre",
                        "Completar el fondo hasta 150 euros y registrar la diferencia antes "
                        "de abrir",
                        "Cobrar solo con tarjeta hasta que llegue el encargado",
                        "Pedir cambio prestado y devolverlo por la tarde",
                    ),
                    correct_a=1,
                    explain_a=(
                        "La diferencia se registra al abrir, nunca al cierre: si no, el "
                        "arqueo del turno no dice nada."
                    ),
                    question_b="Para que sirve el briefing de cinco minutos antes de abrir?",
                    options_b=(
                        "Para repartir las propinas del dia anterior",
                        "Para que todo el turno sepa la carta del dia, las roturas de stock "
                        "y las reservas",
                        "Para fichar la entrada",
                        "Para repasar la limpieza de la sala",
                    ),
                    correct_b=1,
                    explain_b="Carta del dia, roturas y reservas: lo que cambia cada turno.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="recepcion",
        title="Recibir y acomodar al cliente",
        summary=(
            "Los primeros treinta segundos: saludo, reserva, numero de comensales, mesa, "
            "carta, alergenos y agua."
        ),
        outcome="Sentar a una mesa con toda la informacion tomada y sin que nadie espere de pie.",
        criticality=NodeCriticality.RECOMMENDED,
        position=2,
        headings=("Recepcion y acomodo del cliente",),
        ui_format=UiFormat.EXPLANATION,
        estimated_minutes=6,
        skill="atencion_cliente",
        prerequisites=("apertura",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Entra un grupo de cuatro personas mientras estas sirviendo un cafe. "
                        "Que haces?"
                    ),
                    options_a=(
                        "Terminar el servicio y atenderles cuando puedas",
                        "Saludarles en menos de treinta segundos y decirles que ahora mismo "
                        "estas con ellos",
                        "Senalarles una mesa desde lejos",
                        "Esperar a que pidan mesa",
                    ),
                    correct_a=1,
                    explain_a=(
                        "El saludo va en menos de treinta segundos aunque no se les pueda "
                        "atender todavia."
                    ),
                    question_b="Que se pregunta al recibir a un cliente, antes de sentarle?",
                    options_b=(
                        "Si tiene reserva y cuantos son",
                        "Si va a pagar en efectivo o con tarjeta",
                        "Si quiere postre",
                        "Cuanto tiempo se va a quedar",
                    ),
                    correct_b=0,
                    explain_b="Reserva y numero de comensales deciden la mesa.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="comanda",
        title="Tomar la comanda en el TPV",
        summary=(
            "El orden de la mesa, el marcado de alergenos en la linea del plato, la "
            "repeticion en voz alta y el envio por rondas."
        ),
        outcome=(
            "Enviar una comanda a cocina sin errores y con los alergenos visibles en el "
            "sistema."
        ),
        criticality=NodeCriticality.CRITICAL,
        position=3,
        headings=("Toma de comanda en el TPV",),
        ui_format=UiFormat.EXERCISE,
        estimated_minutes=12,
        skill="caja_tpv",
        prerequisites=("recepcion",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Una comensal te dice que es alergica al marisco. Donde queda eso "
                        "registrado para que cocina lo vea?"
                    ),
                    options_a=(
                        "Basta con decirselo al pase de viva voz",
                        "Se marca el alergeno en la linea del plato en el TPV, ademas de "
                        "avisar al pase",
                        "Se apunta en la libreta de la comanda",
                        "No hace falta si el plato que pide no lleva marisco",
                    ),
                    correct_a=1,
                    explain_a=(
                        "La voz se pierde en el pase; la linea del TPV es la que viaja con "
                        "el plato."
                    ),
                    question_b="Por que se repite la comanda en voz alta antes de enviarla?",
                    options_b=(
                        "Para que el cliente vea que estas trabajando",
                        "Para detectar los errores antes de que lleguen a cocina",
                        "Porque lo exige el TPV",
                        "Para ganar tiempo mientras cocina se pone al dia",
                    ),
                    correct_b=1,
                    explain_b="Un error detectado en la mesa cuesta segundos; en el pase, un plato.",
                    template_c=(
                        "La comanda se toma siguiendo siempre el mismo orden de la mesa, en "
                        "sentido ___, para servir despues sin preguntar."
                    ),
                    answer_c="horario",
                    explain_c="Sentido horario, empezando a la izquierda de la puerta.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="tiempos",
        title="Coordinacion con cocina y tiempos",
        summary=(
            "Los tiempos objetivo de salida, cuando se avisa a la mesa y como se anuncian "
            "dos mesas grandes a la vez."
        ),
        outcome="Detectar un retraso antes que el cliente y darle un tiempo concreto.",
        criticality=NodeCriticality.RECOMMENDED,
        position=4,
        headings=("Coordinacion con cocina y tiempos",),
        ui_format=UiFormat.CHART,
        estimated_minutes=8,
        prerequisites=("comanda",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Los segundos de la mesa 7 llevan veinticuatro minutos y el objetivo "
                        "son dieciocho. Que haces?"
                    ),
                    options_a=(
                        "Esperar: cocina ya sabe que va tarde",
                        "Avisar a la mesa antes de que pregunten y darles un tiempo concreto",
                        "Invitar a un chupito sin decir nada",
                        "Anular el plato y ofrecer otro",
                    ),
                    correct_a=1,
                    explain_a=(
                        "Pasados cinco minutos sobre el objetivo se avisa: el cliente perdona "
                        "la espera, no el silencio."
                    ),
                    question_b="Cual es el tiempo objetivo de salida de los primeros?",
                    options_b=("Cinco minutos", "Doce minutos", "Dieciocho minutos", "Media hora"),
                    correct_b=1,
                    explain_b="Doce minutos los primeros, dieciocho los segundos.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="servicio",
        title="Servicio en mesa y seguimiento",
        summary=(
            "Por donde se sirve y se retira, cuando se retira, el repaso a los tres minutos "
            "y la sugerencia de postre y cafe."
        ),
        outcome="Llevar una mesa entera sin que el cliente tenga que pedir nada dos veces.",
        criticality=NodeCriticality.RECOMMENDED,
        position=5,
        headings=("Servicio en mesa y seguimiento",),
        ui_format=UiFormat.EXPLANATION,
        estimated_minutes=7,
        skill="upselling",
        prerequisites=("comanda",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Acabas de retirar los segundos de una mesa de dos. Cual es el "
                        "siguiente paso del protocolo?"
                    ),
                    options_a=(
                        "Llevar la cuenta directamente",
                        "Ofrecer postres y, despues, cafes",
                        "Retirar el mantel",
                        "Esperar a que pidan algo mas",
                    ),
                    correct_a=1,
                    explain_a="Postres y cafes se ofrecen antes de que el cliente pida la cuenta.",
                    question_b="Cuando se retiran los platos de una mesa?",
                    options_b=(
                        "En cuanto alguien termina",
                        "Cuando han terminado todos los comensales",
                        "Solo si el cliente lo pide",
                        "Al llevar la cuenta",
                    ),
                    correct_b=1,
                    explain_b="No se retira hasta que ha terminado toda la mesa.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="cobro",
        title="Cobro y cierre de mesa",
        summary=(
            "Comprobar la cuenta contra lo servido, cobrar en mesa, entregar ticket y cerrar "
            "la mesa en el TPV."
        ),
        outcome="Cobrar una mesa dejandola cerrada en el sistema y con el ticket entregado.",
        criticality=NodeCriticality.CRITICAL,
        position=6,
        headings=("Cobro y cierre de mesa",),
        ui_format=UiFormat.EXERCISE,
        estimated_minutes=10,
        skill="caja_tpv",
        prerequisites=("servicio",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Al cobrar, el cliente te dice que en la cuenta hay un plato que no "
                        "ha pedido. Que haces primero?"
                    ),
                    options_a=(
                        "Decirle que la cuenta ya esta emitida",
                        "Comprobar la comanda en el TPV contra lo servido antes de nada",
                        "Devolverle el importe en efectivo del cajon",
                        "Pedirle que vuelva manana a hablar con el encargado",
                    ),
                    correct_a=1,
                    explain_a="Primero se comprueba; solo despues se decide que se hace.",
                    question_b="Por que hay que cerrar la mesa en el TPV despues de cobrar?",
                    options_b=(
                        "Para que la mesa quede libre en el sistema y el arqueo cuadre",
                        "Para imprimir un segundo ticket",
                        "Para que cocina sepa que se han ido",
                        "No es obligatorio",
                    ),
                    correct_b=0,
                    explain_b=(
                        "Una mesa sin cerrar sigue ocupada en el sistema y descuadra el "
                        "arqueo del turno."
                    ),
                    template_c=(
                        "Despues de cobrar se entrega siempre al cliente el ___, aunque no "
                        "lo pida."
                    ),
                    answer_c="ticket",
                    explain_c="El ticket se entrega siempre.",
                ),
                strict=True,
            )
        ),
    ),
    NodeSpec(
        key="quejas",
        title="Gestion de una queja en mesa",
        summary=(
            "Escuchar, disculparse, resolver en menos de dos minutos y saber cuando hay que "
            "llamar al encargado."
        ),
        outcome="Cerrar una queja en mesa sin escalarla y dejandola anotada en el parte.",
        criticality=NodeCriticality.RECOMMENDED,
        position=7,
        headings=("Incidencias y quejas",),
        ui_format=UiFormat.MIXED,
        estimated_minutes=9,
        skill="gestion_quejas",
        prerequisites=("recepcion",),
        **dict(
            zip(
                ("probe_items", "probe_answer_key"),
                probe(
                    question_a=(
                        "Un cliente se queja de que su plato ha llegado frio. Cual es la "
                        "primera respuesta correcta?"
                    ),
                    options_a=(
                        "Explicarle que la cocina va saturada",
                        "Escuchar sin interrumpir, disculparte y ofrecer cambiarlo de "
                        "inmediato",
                        "Decirle que es la politica de la casa",
                        "Llamar al encargado antes de decir nada",
                    ),
                    correct_a=1,
                    explain_a=(
                        "Escuchar, disculparse y ofrecer solucion en menos de dos minutos. "
                        "Nunca justificar con la politica de la casa."
                    ),
                    question_b="En que caso hay que avisar al encargado antes de comprometer nada?",
                    options_b=(
                        "Siempre que haya una queja",
                        "Cuando la compensacion supera los veinte euros o hay riesgo para la "
                        "salud",
                        "Cuando el cliente sube la voz",
                        "Nunca: la queja la cierra quien atiende la mesa",
                    ),
                    correct_b=1,
                    explain_b="Veinte euros o salud: esos dos limites los decide el encargado.",
                    template_c=(
                        "Toda incidencia de sala se anota en el parte de ___ para que el "
                        "turno siguiente la conozca."
                    ),
                    answer_c="turno",
                    explain_c="El parte de turno.",
                ),
                strict=True,
            )
        ),
    ),
)

COURSE_SALA = DynamicCourseSpec(
    title="Servicio de sala: de la comanda al cobro",
    description=(
        "El proceso completo de un turno de sala, nodo a nodo, con los prerrequisitos que "
        "impiden saltarse el orden."
    ),
    outcome="Llevar un turno de sala completo sin supervision.",
    document_key="sala",
    intent_density=3,
    nodes=_SALA_NODES,
)

DYNAMIC_COURSES: tuple[DynamicCourseSpec, ...] = (COURSE_ALERGENOS, COURSE_SALA)


# ------------------------------------------------------------------ the v1 static course --
@dataclass(frozen=True)
class StaticLessonSpec:
    title: str
    content: str
    exercises: tuple[tuple[ExerciseType, dict], ...] = ()


@dataclass(frozen=True)
class StaticModuleSpec:
    title: str
    summary: str
    lessons: tuple[StaticLessonSpec, ...]


STATIC_COURSE_TITLE = "Manejo de caja y arqueo diario (v1 estatico)"
STATIC_COURSE_MODULES: tuple[StaticModuleSpec, ...] = (
    StaticModuleSpec(
        title="Caja y cobros",
        summary="Fondo de caja y medios de pago.",
        lessons=(
            StaticLessonSpec(
                title="El fondo de caja",
                content=(
                    "## El fondo de caja\n\n"
                    "El fondo de caja de La Espiga es de **150 euros** en cambio: monedas y "
                    "billetes pequenos.\n\n"
                    "Se cuenta **al abrir y al cerrar**, siempre por la misma persona que "
                    "firma el parte. Si al abrir no cuadra, se completa y se registra la "
                    "diferencia **antes** de abrir, nunca al cierre.\n"
                ),
                exercises=(
                    (
                        ExerciseType.TEST,
                        {
                            "question": "De cuanto es el fondo de caja?",
                            "options": [
                                "100 euros",
                                "150 euros",
                                "200 euros",
                                "Depende del turno",
                            ],
                            "correct": 1,
                            "explanation": "150 euros en cambio, fijos para todos los turnos.",
                        },
                    ),
                ),
            ),
            StaticLessonSpec(
                title="Medios de pago",
                content=(
                    "## Medios de pago\n\n"
                    "Se admite efectivo, tarjeta y pago movil.\n\n"
                    "- El **ticket se entrega siempre**, aunque el cliente no lo pida.\n"
                    "- Los vales de comida se registran como **medio de pago propio**, "
                    "nunca como descuento: si no, el arqueo no cuadra.\n"
                ),
            ),
        ),
    ),
    StaticModuleSpec(
        title="Cierre",
        summary="El arqueo y que hacer con un descuadre.",
        lessons=(
            StaticLessonSpec(
                title="El arqueo de cierre",
                content=(
                    "## El arqueo\n\n"
                    "El arqueo compara el **efectivo contado** con el **desglose por medio "
                    "de pago** que imprime el TPV.\n\n"
                    "Se hace con la caja ya cerrada al publico y sin interrupciones.\n"
                ),
                exercises=(
                    (
                        ExerciseType.TEST,
                        {
                            "question": "Que se compara en el arqueo de cierre?",
                            "options": [
                                "El efectivo contado con el desglose del TPV",
                                "Las propinas con las ventas",
                                "El fondo de caja con el del dia anterior",
                                "Los tickets impresos con las reservas",
                            ],
                            "correct": 0,
                            "explanation": "Efectivo contado contra desglose del TPV.",
                        },
                    ),
                    (
                        ExerciseType.FILL_BLANK,
                        {
                            "template": (
                                "La diferencia maxima tolerada en el arqueo es de ___ euros."
                            ),
                            "blanks": ["5"],
                            "explanation": "Por encima de cinco euros se avisa al encargado.",
                        },
                    ),
                ),
            ),
            StaticLessonSpec(
                title="Descuadres",
                content=(
                    "## Descuadres\n\n"
                    "- Hasta **5 euros**: se anota en el parte y se cierra.\n"
                    "- Por encima de 5 euros: **se avisa al encargado** y se revisan los "
                    "tickets del turno uno a uno. La caja no se cierra sin el.\n"
                ),
            ),
        ),
    ),
)

#: Which employees get which course. Keys are ``email_local``.
ENROLLMENTS: dict[str, tuple[str, ...]] = {
    COURSE_ALERGENOS.title: tuple(spec.email_local for spec in EMPLOYEES),
    COURSE_SALA.title: ("aitana.souto", "diego.varela", "noa.pereira", "lucia.fernandez"),
    # STATIC_COURSE_TITLE removed — v2 only
}


# --------------------------------------------------------------------------------------
# Pure validation — the same functions the gate of §11.1 runs
# --------------------------------------------------------------------------------------
class _GraphNode:
    """The structural minimum ``validate_schema_graph`` reads. No ORM, no database."""

    __slots__ = (
        "archived",
        "criticality",
        "id",
        "position",
        "reviewed_at",
        "seed_lesson_id",
        "source_document_id",
        "summary",
    )

    def __init__(self, spec: NodeSpec) -> None:
        self.id = spec.key
        self.summary = spec.summary
        self.criticality = spec.criticality
        self.position = spec.position
        self.source_document_id = spec.key  # every seeded node carries its document
        self.seed_lesson_id = None
        self.reviewed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.archived = False


def check_specs() -> None:
    """Raise ``ValidationError``/``AssertionError`` unless every spec would pass the gate.

    Called by ``seed()`` before anything is written and by ``tests/test_seed_demo_v2.py``
    without a database. Two different validations, both from production code:

    * ``validate_probe_items`` — the §7.1 item contract, including "a ``critical`` node
      needs the constructed tie-break".
    * ``validate_schema_graph`` — the §11.1 blocking rules: acyclic, contiguous positions,
      at least one ``critical`` node, no orphan prerequisites, every node with a summary.
    """
    for course in DYNAMIC_COURSES:
        keys = {node.key for node in course.nodes}
        assert len(keys) == len(course.nodes), f"{course.title}: duplicate node keys"
        for node in course.nodes:
            validate_probe_items(node.probe_items, node.probe_answer_key, node.criticality)
            for prerequisite in node.prerequisites:
                assert prerequisite in keys, (
                    f"{course.title}/{node.key}: unknown prerequisite {prerequisite!r}"
                )
            if node.seed_lesson is not None:
                titles = [title for title, _ in course.backup_lessons]
                assert node.seed_lesson in titles, (
                    f"{course.title}/{node.key}: no backup lesson {node.seed_lesson!r}"
                )
        errors = validate_schema_graph(
            [_GraphNode(node) for node in course.nodes],
            {node.key: list(node.prerequisites) for node in course.nodes},
        )
        assert not errors, f"{course.title}: the schema would not validate: {errors}"

    known_skills = {name for defs in TAXONOMY.values() for name, _ in defs}
    for course in DYNAMIC_COURSES:
        for node in course.nodes:
            if node.skill is not None:
                assert node.skill in known_skills, f"unknown skill {node.skill!r}"
    for employee in EMPLOYEES:
        for skill_name in employee.skills:
            assert skill_name in known_skills, f"unknown skill {skill_name!r}"

    titles = {course.title for course in DYNAMIC_COURSES}
    assert set(ENROLLMENTS) == titles, "ENROLLMENTS does not cover every seeded course"
    emails = {spec.email_local for spec in EMPLOYEES}
    for course_title, assigned in ENROLLMENTS.items():
        for email_local in assigned:
            assert email_local in emails, f"{course_title}: unknown employee {email_local!r}"


# --------------------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------------------
async def _ensure_org(session) -> Organization:
    org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
    if org is None:
        raise SystemExit(
            "No hay ninguna organizacion. Arranca la API una vez (crea la organizacion y "
            "el admin desde ADMIN_EMAIL/ADMIN_PASSWORD) y vuelve a lanzar el seed."
        )
    # Only a placeholder name is replaced: a real deployment keeps the name it chose.
    if org.name in PLACEHOLDER_ORG_NAMES:
        org.name = DEMO_ORG_NAME
    org_settings = dict(org.settings or {})
    if not org_settings.get("sector"):
        # Drives the onboarding role suggestions (src/schemas/onboarding.py).
        org_settings["sector"] = DEMO_SECTOR
        org.settings = org_settings
    return org


async def _ensure_admin(session, org: Organization) -> User:
    admin = (
        await session.execute(
            select(User)
            .where(User.org_id == org.id, User.role == UserRole.ADMIN)
            .order_by(User.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if admin is None:
        raise SystemExit(
            "No hay ningun administrador. Pon ADMIN_EMAIL y ADMIN_PASSWORD en el .env, "
            "reinicia la API y vuelve a lanzar el seed."
        )
    return admin


async def _ensure_taxonomy(session, org: Organization) -> dict[str, Skill]:
    """Categories and skills of the v1 taxonomy, get-or-created. Shared with ``seed_demo``."""
    skills: dict[str, Skill] = {}
    for position, (category_name, definitions) in enumerate(TAXONOMY.items()):
        category = (
            await session.execute(
                select(SkillCategory).where(
                    SkillCategory.org_id == org.id, SkillCategory.name == category_name
                )
            )
        ).scalar_one_or_none()
        if category is None:
            category = SkillCategory(org_id=org.id, name=category_name, position=position)
            session.add(category)
            await session.flush()
        for name, description in definitions:
            skill = (
                await session.execute(
                    select(Skill).where(Skill.org_id == org.id, Skill.name == name)
                )
            ).scalar_one_or_none()
            if skill is None:
                skill = Skill(
                    org_id=org.id,
                    category_id=category.id,
                    name=name,
                    description=description,
                )
                session.add(skill)
                await session.flush()
            skills[name] = skill
    return skills


async def _ensure_employee(
    session, org: Organization, spec: EmployeeSpec, skills: dict[str, Skill]
) -> tuple[User, bool]:
    user = (
        await session.execute(select(User).where(User.email == spec.email))
    ).scalar_one_or_none()
    created = False
    if user is None:
        from fastapi_users.password import PasswordHelper

        user = User(
            email=spec.email,
            hashed_password=PasswordHelper().hash(DEMO_PASSWORD),
            org_id=org.id,
            full_name=spec.full_name,
            role=UserRole.EMPLOYEE,
            hired_at=spec.hired_at,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        created = True

    for skill_name, level in spec.skills.items():
        skill = skills.get(skill_name)
        if skill is None:
            continue
        existing = (
            await session.execute(
                select(UserSkill).where(
                    UserSkill.user_id == user.id, UserSkill.skill_id == skill.id
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                UserSkill(
                    user_id=user.id,
                    skill_id=skill.id,
                    level=level,
                    source="demo_seed_v2",
                )
            )
    return user, created


async def _ensure_profile(session, user: User, spec: EmployeeSpec) -> None:
    """Populate ``learner_profiles`` exactly as the onboarding endpoint would.

    Through ``LearnerProfileService.complete_onboarding`` on purpose: the seeded profile is
    then the same shape the wizard writes (including ``tutor_notes.context`` and the
    ``users.learning_profile`` mirror), instead of a hand-built row that drifts from it.
    """
    if not spec.has_profile:
        return
    repo = LearnerProfileRepository(session)
    if (await repo.get_by_user(user.id)) is not None:
        return
    service = LearnerProfileService(repo, LearningEventRepository(session))
    profile = await service.complete_onboarding(
        user=user,
        role_title=spec.role_title,
        sector=DEMO_SECTOR,
        goal=spec.goal,
        experience_level=spec.experience,
        preset=spec.preset,
        accessibility=spec.accessibility or None,
    )
    if spec.nodes_completed:
        profile.nodes_completed = spec.nodes_completed
    if spec.format_vector:
        profile.format_vector = dict(spec.format_vector)
        profile.format_vector_updated_at = datetime.now(timezone.utc)
    await session.flush()


def _write_document_file(org_id: uuid.UUID, doc_id: uuid.UUID, spec: DocumentSpec) -> str:
    """Best effort: drop the markdown where an uploaded file would live.

    ``full_text`` in the row is what the runtime reads, so a failure here (read-only volume,
    permissions) is a warning and not an error: the demo works without the file on disk.
    """
    try:
        target_dir = Path(settings.UPLOAD_DIR) / str(org_id) / str(doc_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / spec.filename
        target.write_text(spec.full_text, encoding="utf-8")
        return str(target)
    except OSError as exc:  # noqa: BLE001 - a missing file must not stop the seed
        logger.warning("Could not write %s to disk: %s", spec.filename, exc)
        return ""


async def _ensure_document(
    session, org: Organization, admin: User, spec: DocumentSpec
) -> Document:
    document = (
        await session.execute(
            select(Document).where(Document.org_id == org.id, Document.title == spec.title)
        )
    ).scalar_one_or_none()
    if document is not None:
        return document

    full_text = spec.full_text
    document = Document(
        org_id=org.id,
        uploaded_by=admin.id,
        title=spec.title,
        storage_path="",
        file_type="md",
        # <= 5 pages is the `full_text` branch of load_source_context: no embeddings needed.
        page_count=spec.page_count,
        size_bytes=len(full_text.encode("utf-8")),
        full_text=full_text,
        status=DocumentStatus.READY,
    )
    session.add(document)
    await session.flush()
    document.storage_path = _write_document_file(org.id, document.id, spec)
    return document


def _parsed_sections(spec: DocumentSpec) -> list[ParsedSection]:
    """The spec's sections in the shape ``chunk_sections`` expects.

    Page numbers are apportioned evenly over ``page_count`` rather than invented per
    section: a citation that says "pag. 2" has to be *roughly* true, and the seed has no
    real pagination to be exactly true to.
    """
    total = max(1, len(spec.sections))
    per_page = max(1, (total + spec.page_count - 1) // spec.page_count)
    return [
        ParsedSection(
            heading=heading,
            level=2,
            content=body,
            page_start=min(spec.page_count, index // per_page + 1),
            page_end=min(spec.page_count, index // per_page + 1),
            position=index,
        )
        for index, (heading, body) in enumerate(spec.sections)
    ]


async def _ensure_chunks(session, org: Organization, document: Document, spec: DocumentSpec) -> int:
    """Chunk and embed a seeded document, exactly as ingestion would have.

    **Why a <= 5-page document is chunked at all.** The runtime does not need it: those
    documents take the ``full_text`` branch of ``load_source_context`` (§4.2) and that is
    still the branch the node graph uses. The tutor chat is the other consumer, it is RAG
    over ``document_chunks``, and until today the demo gave it an empty table — so the
    ``chunked`` half of the product was never exercised by the thing everybody actually
    clicks on. Chunking here costs nothing at runtime and makes that path real.

    **Why the chat is still correct when this does nothing.** It is best effort: an org
    with no embedding provider gets a warning and zero chunks, which is precisely the
    state ``src/services/ingestion.py`` leaves behind when embedding fails. The tutor's
    ladder (``src/services/retrieval.py``) treats that as rung 2 and answers from
    ``full_text``. The seed is not allowed to be the reason the chat works.

    Idempotent: a document that already has chunks is left alone.
    """
    repo = DocumentChunkRepository(session)
    if await repo.count_for_document(document.id):
        return 0

    chunks = chunk_sections(_parsed_sections(spec), spec.title)
    if not chunks:
        return 0

    config = resolve_embedding_config(dict(org.settings or {}))
    embedder = maybe_fixture_embedder(config)
    try:
        vectors = await embedder.embed_texts([c.content for c in chunks], prefix="passage: ")
    except Exception as exc:  # noqa: BLE001 - the demo must seed without an embedder
        logger.warning(
            "No embeddings for %s (%s). The document keeps its full_text and the tutor "
            "answers from it; RAG will have nothing to retrieve.",
            spec.title,
            exc,
        )
        return 0

    for chunk, vector in zip(chunks, vectors, strict=True):
        await repo.add_chunk(
            document_id=document.id,
            content=chunk.content,
            embedding=vector,
            chunk_index=chunk.chunk_index,
            chunk_metadata=chunk.metadata,
        )
    document.embedding_model = config.model
    document.embedding_dim = config.dimensions
    await session.flush()
    return len(chunks)


async def _ensure_module_tree(
    session,
    course: Course,
    modules: tuple[StaticModuleSpec, ...],
    *,
    start_position: int = 1,
) -> dict[str, Lesson]:
    """Get-or-create v1 modules/lessons/exercises. Returns the lessons by title."""
    lessons_by_title: dict[str, Lesson] = {}
    for module_index, module_spec in enumerate(modules, start=start_position):
        module = (
            await session.execute(
                select(Module).where(
                    Module.course_id == course.id, Module.title == module_spec.title
                )
            )
        ).scalar_one_or_none()
        if module is None:
            module = Module(
                course_id=course.id,
                title=module_spec.title,
                summary=module_spec.summary,
                position=module_index,
            )
            session.add(module)
            await session.flush()

        for lesson_index, lesson_spec in enumerate(module_spec.lessons, start=1):
            lesson = (
                await session.execute(
                    select(Lesson).where(
                        Lesson.module_id == module.id, Lesson.title == lesson_spec.title
                    )
                )
            ).scalar_one_or_none()
            if lesson is None:
                lesson = Lesson(
                    module_id=module.id,
                    title=lesson_spec.title,
                    content=lesson_spec.content,
                    position=lesson_index,
                )
                session.add(lesson)
                await session.flush()
                for exercise_index, (kind, content) in enumerate(lesson_spec.exercises, start=1):
                    session.add(
                        Exercise(
                            lesson_id=lesson.id,
                            type=kind,
                            content=content,
                            position=exercise_index,
                        )
                    )
            lessons_by_title[lesson_spec.title] = lesson
    return lessons_by_title


async def _ensure_static_course(
    session, org: Organization, admin: User, document: Document
) -> Course:
    course = (
        await session.execute(
            select(Course).where(Course.org_id == org.id, Course.title == STATIC_COURSE_TITLE)
        )
    ).scalar_one_or_none()
    if course is None:
        course = Course(
            org_id=org.id,
            created_by=admin.id,
            source_document_id=document.id,
            title=STATIC_COURSE_TITLE,
            description=(
                "El mismo tipo de contenido, por el camino v1: modulos y lecciones en "
                "Markdown, iguales para todo el mundo. Sirve para comparar."
            ),
            outcome="Cerrar la caja de un turno sin descuadres.",
            status=ContentStatus.PUBLISHED,
            # Explicit, even though these are the defaults: this course is the control group.
            delivery_mode=CourseDeliveryMode.STATIC,
            schema_status=CourseSchemaStatus.DRAFT,
        )
        session.add(course)
        await session.flush()
    await _ensure_module_tree(session, course, STATIC_COURSE_MODULES)
    return course


async def _ensure_dynamic_course(
    session,
    org: Organization,
    admin: User,
    spec: DynamicCourseSpec,
    document: Document,
    skills: dict[str, Skill],
    *,
    refresh: bool,
) -> tuple[Course, list[CourseNode]]:
    now = datetime.now(timezone.utc)
    course = (
        await session.execute(
            select(Course).where(Course.org_id == org.id, Course.title == spec.title)
        )
    ).scalar_one_or_none()
    if course is None:
        course = Course(
            org_id=org.id,
            created_by=admin.id,
            source_document_id=document.id,
            title=spec.title,
            description=spec.description,
            outcome=spec.outcome,
            status=ContentStatus.PUBLISHED,
            intent_density=spec.intent_density,
            # Written straight to the post-gate state: the schema below is already valid,
            # already reviewed and already validated (see the checks in `seed`).
            delivery_mode=CourseDeliveryMode.DYNAMIC,
            schema_status=CourseSchemaStatus.VALIDATED,
            schema_validated_by=admin.id,
            schema_validated_at=now,
        )
        session.add(course)
        await session.flush()

    backup_lessons: dict[str, Lesson] = {}
    if spec.backup_module and spec.backup_lessons:
        backup_lessons = await _ensure_module_tree(
            session,
            course,
            (
                StaticModuleSpec(
                    title=spec.backup_module,
                    summary=(
                        "Respaldo v1 de este curso. Solo se sirve si la generacion falla "
                        "dos veces (modo degradado) o con el flag apagado."
                    ),
                    lessons=tuple(
                        StaticLessonSpec(title=title, content=content)
                        for title, content in spec.backup_lessons
                    ),
                ),
            ),
        )

    nodes: dict[str, CourseNode] = {}
    for node_spec in spec.nodes:
        node = (
            await session.execute(
                select(CourseNode).where(
                    CourseNode.course_id == course.id, CourseNode.title == node_spec.title
                )
            )
        ).scalar_one_or_none()
        skill = skills.get(node_spec.skill) if node_spec.skill else None
        seed_lesson = backup_lessons.get(node_spec.seed_lesson) if node_spec.seed_lesson else None
        if node is None:
            node = CourseNode(
                org_id=org.id,
                course_id=course.id,
                skill_id=skill.id if skill else None,
                seed_lesson_id=seed_lesson.id if seed_lesson else None,
                title=node_spec.title,
                summary=node_spec.summary,
                outcome=node_spec.outcome,
                criticality=node_spec.criticality,
                position=node_spec.position,
                source_document_id=document.id,
                source_headings=list(node_spec.headings),
                mastery_threshold=default_threshold_for(node_spec.criticality),
                default_ui_format=node_spec.ui_format,
                probe_items=node_spec.probe_items,
                probe_answer_key=node_spec.probe_answer_key,
                estimated_minutes=node_spec.estimated_minutes,
                # Reviewed by the admin: without this the runtime answers 409
                # node_not_reviewed on every node (§3.2).
                reviewed_at=now,
                reviewed_by=admin.id,
            )
            session.add(node)
            await session.flush()
        elif refresh:
            node.summary = node_spec.summary
            node.outcome = node_spec.outcome
            node.criticality = node_spec.criticality
            node.position = node_spec.position
            node.source_headings = list(node_spec.headings)
            node.default_ui_format = node_spec.ui_format
            node.estimated_minutes = node_spec.estimated_minutes
            node.mastery_threshold = default_threshold_for(node_spec.criticality)
            node.probe_items = node_spec.probe_items
            node.probe_answer_key = node_spec.probe_answer_key
            node.seed_lesson_id = seed_lesson.id if seed_lesson else node.seed_lesson_id
            node.reviewed_at = now
            node.reviewed_by = admin.id
        nodes[node_spec.key] = node

        if skill is not None:
            link = (
                await session.execute(
                    select(CourseSkill).where(
                        CourseSkill.course_id == course.id, CourseSkill.skill_id == skill.id
                    )
                )
            ).scalar_one_or_none()
            if link is None:
                session.add(CourseSkill(course_id=course.id, skill_id=skill.id))

    for node_spec in spec.nodes:
        for prerequisite_key in node_spec.prerequisites:
            node_id = nodes[node_spec.key].id
            prerequisite_id = nodes[prerequisite_key].id
            existing = (
                await session.execute(
                    select(CourseNodePrerequisite).where(
                        CourseNodePrerequisite.node_id == node_id,
                        CourseNodePrerequisite.prerequisite_node_id == prerequisite_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    CourseNodePrerequisite(
                        node_id=node_id, prerequisite_node_id=prerequisite_id
                    )
                )

    if refresh:
        # `schema_version` is part of the cache_key, so bumping it invalidates every render
        # derived from the old wording without deleting a single row. Clearing the pin is
        # the other half: `GET /nodes/{id}/render` serves `active_render_id` verbatim
        # (Vision A, §3.3) and would keep showing the old screen otherwise.
        course.schema_version = int(course.schema_version or 1) + 1
        await session.execute(
            update(LearnerNodeState)
            .where(LearnerNodeState.node_id.in_([node.id for node in nodes.values()]))
            .values(active_render_id=None, render_pinned=False)
        )

    await session.flush()
    return course, [nodes[node_spec.key] for node_spec in spec.nodes]


async def _assert_validated(session, course: Course, nodes: list[CourseNode]) -> None:
    """Re-run the §11.1 gate against the rows that were actually written.

    ``check_specs`` proves the *specs* are valid; this proves the *database* is, which is
    not the same claim once a node has been edited by hand between two runs.
    """
    prerequisites: dict[uuid.UUID, list[uuid.UUID]] = {}
    for node in nodes:
        rows = (
            await session.execute(
                select(CourseNodePrerequisite.prerequisite_node_id).where(
                    CourseNodePrerequisite.node_id == node.id
                )
            )
        ).scalars().all()
        prerequisites[node.id] = list(rows)
    errors = validate_schema_graph(nodes, prerequisites)
    if errors:
        raise SystemExit(
            f"El esquema de '{course.title}' no pasa la validacion de §11.1: {errors}"
        )
    for node in nodes:
        validate_probe_items(node.probe_items, node.probe_answer_key, node.criticality)


async def _ensure_enrollment(session, user: User, course: Course, admin: User) -> None:
    existing = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id, Enrollment.course_id == course.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(Enrollment(user_id=user.id, course_id=course.id, assigned_by=admin.id))


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
async def seed(*, refresh: bool = False) -> None:
    check_specs()

    async with async_session_factory() as session:
        org = await _ensure_org(session)
        admin = await _ensure_admin(session, org)
        skills = await _ensure_taxonomy(session, org)

        users: dict[str, User] = {}
        created_users: list[str] = []
        for spec in EMPLOYEES:
            user, created = await _ensure_employee(session, org, spec, skills)
            await _ensure_profile(session, user, spec)
            users[spec.email_local] = user
            if created:
                created_users.append(spec.email)

        documents: dict[str, Document] = {}
        chunk_counts: dict[str, int] = {}
        for spec in DOCUMENTS:
            document = await _ensure_document(session, org, admin, spec)
            documents[spec.key] = document
            chunk_counts[spec.title] = await _ensure_chunks(session, org, document, spec)

        courses: dict[str, Course] = {}

        node_counts: dict[str, int] = {}
        for spec in DYNAMIC_COURSES:
            course, nodes = await _ensure_dynamic_course(
                session,
                org,
                admin,
                spec,
                documents[spec.document_key],
                skills,
                refresh=refresh,
            )
            await _assert_validated(session, course, nodes)
            courses[spec.title] = course
            node_counts[spec.title] = len(nodes)

        for course_title, assigned in ENROLLMENTS.items():
            course = courses[course_title]
            for email_local in assigned:
                await _ensure_enrollment(session, users[email_local], course, admin)

        await session.commit()
        _report(
            org,
            admin,
            users,
            courses,
            node_counts,
            created_users,
            chunk_counts,
            refresh=refresh,
        )

    await engine.dispose()


def _report(
    org: Organization,
    admin: User,
    users: dict[str, User],
    courses: dict[str, Course],
    node_counts: dict[str, int],
    created_users: list[str],
    chunk_counts: dict[str, int],
    *,
    refresh: bool,
) -> None:
    line = "-" * 78
    print()
    print(line)
    print(f"  {org.name}   (sector: {(org.settings or {}).get('sector')})")
    print(line)
    if refresh:
        print("  MODO --refresh: nodos reescritos, schema_version subido, renders sin fijar.")
        print()
    print(f"  Admin:     {admin.email}   (contrasena: la de tu .env, ADMIN_PASSWORD)")
    print(f"  Empleados: contrasena unica -> {DEMO_PASSWORD}")
    print()
    for spec in EMPLOYEES:
        user = users[spec.email_local]
        flag = "NUEVO" if user.email in created_users else "     "
        profile = "perfil poblado" if spec.has_profile else "SIN perfil (haz el onboarding)"
        print(f"  [{flag}] {spec.email}")
        print(f"          {spec.job} - {profile}")
        if spec.note:
            print(f"          {spec.note}")
    print()
    if any(chunk_counts.values()):
        print("  Documentos indexados para el tutor (RAG):")
        for title, count in chunk_counts.items():
            if count:
                print(f"    - {title}: {count} fragmentos")
        print()
    print("  Cursos:")
    for title, course in courses.items():
        mode = str(getattr(course.delivery_mode, "value", course.delivery_mode))
        status = str(getattr(course.schema_status, "value", course.schema_status))
        count = node_counts.get(title)
        shape = f"{count} nodos" if count else "modulos/lecciones v1"
        print(f"    - {title}")
        print(f"      {mode} / {status} / {shape}   id={course.id}")
        if mode == "dynamic":
            print(f"      esquema: /admin/curso/{course.id}/esquema")
        print(f"      alumno:  /empleado/curso/{course.id}")
    print()
    print("  Los cursos dinamicos se ven con delivery_mode='dynamic' y schema validado.")
    print("  Guia paso a paso: docs/TESTING.md")
    print(line)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.seed_demo_v2",
        description="Siembra la demo v2 (cursos dinamicos). Idempotente.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Reescribe los nodos ya existentes con lo que diga este fichero, sube "
            "schema_version (invalida la cache de renders) y suelta los renders fijados. "
            "El progreso de los aprendices se conserva."
        ),
    )
    args = parser.parse_args()

    # Windows consoles are cp1252 by default and the summary carries no accents, but a
    # company name typed by the owner might: never let printing be what fails.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    print()
    print("SkillNet - sembrando la demo v2 (cursos dinamicos)...")
    asyncio.run(seed(refresh=args.refresh))


if __name__ == "__main__":
    main()
