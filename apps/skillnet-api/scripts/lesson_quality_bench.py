#!/usr/bin/env python
"""Banco de calidad de LECCIONES: marca violaciones de rubrica y saca un digest.

Para que sirve
==============

``quality_bench.py`` mide si la generacion **funciona** (acierto a la primera,
reparado, fallback, latencia, coste). Este banco mide si la leccion **esta bien
hecha**: coge el ``ui_spec`` servido de cada nodo y marca, uno por uno, los
defectos de la rubrica (``docs/design/rubrica-calidad-leccion.md``) que hasta ahora
descubriamos a mano, curso a curso. En vez de "esta pantalla no me gusta", saca
"nodo 3: DidactGlossary presente + sin interaccion", y ademas los totales, para que
la calidad sea **medible en el tiempo** y una regresion salte sola.

Es un instrumento de MEDIDA, de solo lectura sobre ``src/``: no arregla nada, no
escribe en la base de datos, no modifica renders. Solo mira y cuenta.

Que marca (los flags)
=====================

Por nodo, mirando el ``ui_spec`` canonico servido:

- ``node_not_ready``      el render no esta ``ready`` (failed / fallback / sin fila).
- ``episode_declined``    el episodio se declino (con el motivo, p.ej.
                          ``missing_knowledge_pack``, ``evidence_policy:...``).
- ``status_fallback``     acabo en fallback / no se sirvio un spec valido.
- ``passive_reveal``      hay un componente que esconde info tras un clic sin obligar
                          a pensar: ``HintReveal`` o ``DidactWorkedExample``
                          (principio 1 de la rubrica).
- ``didact_glossary``     hay ``DidactGlossary`` (debe desaparecer: Curio cubre las
                          definiciones).
- ``flashcard_as_closer`` ``Flashcard`` usada como cierre/evaluacion (debe ser solo
                          contenido, principio 4).
- ``screen_overcrowded``  una pantalla con demasiados bloques (viola el "un foco").
- ``missing_interaction`` una pantalla sin ningun elemento con el que actuar
                          (principio 4: toda leccion interactua de verdad).

Por curso:

- ``assessment_not_varied`` todos los nodos evaluan con el MISMO tipo (principio 2:
                            el componente se elige por lo que el alumno tiene que hacer).

Como se ejecuta
===============

    # 1) Autocomprobacion: mete specs sinteticos con defectos conocidos por el
    #    checker y verifica que cada flag salta. Prueba que las comprobaciones
    #    detectan lo que dicen detectar. Sin red, sin base de datos, sin clave.
    uv run python scripts/lesson_quality_bench.py --self-test

    # 2) En vivo, de solo lectura: inspecciona los renders REALES ya generados por
    #    el pipeline (DeepSeek) que estan en Postgres. No genera nada, no cuesta nada.
    uv run python scripts/lesson_quality_bench.py --db

    # 3) Offline: genera los nodos por el pipeline real con FixtureLLMService y los
    #    inspecciona. Prueba la ruta generar->inspeccionar de punta a punta sin clave.
    uv run python scripts/lesson_quality_bench.py --pipeline --offline

    # 4) En vivo por el pipeline (DeepSeek). Necesita LLM_API_KEY y cuesta dinero.
    uv run python scripts/lesson_quality_bench.py --pipeline

Cada modo saca el mismo DIGEST: por curso/nodo los flags, y al final los totales
(cuantos nodos limpios frente a marcados, y por categoria). Con ``--json <ruta>`` se
guarda el digest entero para comparar entre ejecuciones.

Naturalezas de contenido
========================

El corpus del pipeline (``quality_bench.CORPUS``) ya cubre naturalezas distintas, que
es justo lo que la rubrica pide medir (§ "el norte"): un procedimiento (``extintor``,
``apertura-cierre-caja``), un tema de conocimiento/hechos (``alergenos-hosteleria``,
``proteccion-datos``), un tema de datos/comparacion (``higiene-alimentaria`` -> chart),
y una habilidad fisica (``prevencion-riesgos`` -> manipulacion de cargas). Por defecto
``--pipeline`` toma esos cuatro; ``--db`` toma los cursos reales con mas renders listos.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))


# --------------------------------------------------------------------------------------
# Catalogo: clasificacion de componentes (fuente de verdad: src/render/kit.py)
# --------------------------------------------------------------------------------------
#
# El catalogo de kit.py no marca "interactivo" ni "evaluacion" como un flag, asi que hay
# que derivarlo. Estas constantes son la derivacion. Cuando kit.py esta importable, se
# comprueba que los nombres siguen existiendo (evita que el catalogo cambie por debajo y
# el banco mida un componente que ya no se llama asi); si no, se usan tal cual para que
# ``--db`` y ``--self-test`` funcionen sin el paquete.

CONTAINER_TYPES: frozenset[str] = frozenset({"Stack", "Card"})

#: Componentes que exigen que el aprendiz HAGA algo (responder, arrastrar, revelar,
#: consultar, practicar, jugar). Todo lo demas es contenido pasivo.
INTERACTIVE_TYPES: frozenset[str] = frozenset({
    "QuizItem", "DragOrder", "Flashcard", "HintReveal", "DidactGlossary",
    "DidactWorkedExample", "AudioExplanation", "PronunciationExercise",
    "LearningExperience", "DidactActivity",
})

#: Componentes que reclaman la funcion EVALUAR en kit.py: son evaluacion real.
ASSESSMENT_TYPES: frozenset[str] = frozenset({
    "QuizItem", "DragOrder", "DidactActivity", "LearningExperience",
})

#: Esconden informacion tras un clic. La rubrica (principio 1) los marca para revisar:
#: pueden estar justificados (un ejemplo para razonar), pero por defecto son sospechosos.
PASSIVE_REVEAL_TYPES: frozenset[str] = frozenset({"HintReveal", "DidactWorkedExample"})

#: Maximo de bloques por pantalla antes de considerarla recargada (viola "un foco").
#: El contrato de OpenUI ya limita a 5 hijos del root; esto vigila el caso general de
#: una pantalla-contenedor con demasiado dentro.
DEFAULT_MAX_BLOCKS = 6


def verify_catalog() -> list[str]:
    """Si kit.py esta disponible, comprueba que los nombres clasificados existen."""
    warnings: list[str] = []
    try:
        from src.render.kit import COMPONENT_NAMES
    except Exception as exc:  # noqa: BLE001 - el paquete puede no estar importable
        return [f"catalogo no verificado (kit.py no importable: {type(exc).__name__})"]
    known = set(COMPONENT_NAMES)
    for label, names in (
        ("CONTAINER_TYPES", CONTAINER_TYPES),
        ("INTERACTIVE_TYPES", INTERACTIVE_TYPES),
        ("ASSESSMENT_TYPES", ASSESSMENT_TYPES),
        ("PASSIVE_REVEAL_TYPES", PASSIVE_REVEAL_TYPES),
    ):
        drift = sorted(n for n in names if n not in known)
        if drift:
            warnings.append(f"{label}: nombres que ya no existen en el catalogo: {drift}")
    return warnings


# --------------------------------------------------------------------------------------
# Recorrido del ui_spec (lista plana de componentes + refs por id)
# --------------------------------------------------------------------------------------
#
# Un ui_spec es {root, format, version, components:[{id,type,props,children:[id...]}]}.
# Es una lista plana con referencias por id, no un arbol anidado. El root es un
# contenedor; sus children son ids que se resuelven en components.


def _component_index(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for comp in spec.get("components") or []:
        if isinstance(comp, dict) and isinstance(comp.get("id"), str):
            out[comp["id"]] = comp
    return out


def _reachable_ids(spec: dict[str, Any]) -> list[str]:
    """DFS estable desde root; devuelve ids alcanzables, en orden de aparicion."""
    index = _component_index(spec)
    root = spec.get("root")
    order: list[str] = []
    seen: set[str] = set()

    def walk(cid: str) -> None:
        if cid in seen or cid not in index:
            return
        seen.add(cid)
        order.append(cid)
        for child in index[cid].get("children") or []:
            if isinstance(child, str):
                walk(child)

    if isinstance(root, str):
        walk(root)
    return order


@dataclass(frozen=True)
class Screen:
    """Una pantalla: el contenedor que la envuelve y sus bloques (no contenedores)."""

    container_id: str
    block_types: tuple[str, ...]  # tipos de los bloques, en orden de lectura


def screens_of(spec: dict[str, Any]) -> list[Screen]:
    """Descompone el spec en pantallas.

    Un ui_spec == una pantalla (el root Stack la envuelve). Pero si el root agrupa solo
    contenedores (Cards), cada contenedor es una sub-pantalla con su propio foco. Se
    tratan esos dos casos para que "un bloque por foco" se mida bien en ambos.
    """
    index = _component_index(spec)
    root = spec.get("root")
    if not isinstance(root, str) or root not in index:
        return []

    root_children = [c for c in (index[root].get("children") or []) if isinstance(c, str)]
    child_comps = [index[c] for c in root_children if c in index]
    all_containers = bool(child_comps) and all(
        c.get("type") in CONTAINER_TYPES for c in child_comps
    )

    def blocks_under(container_id: str) -> tuple[str, ...]:
        # Bloques = componentes alcanzables no-contenedor bajo este contenedor.
        order: list[str] = []
        seen: set[str] = set()

        def walk(cid: str) -> None:
            if cid in seen or cid not in index:
                return
            seen.add(cid)
            comp = index[cid]
            if comp.get("type") not in CONTAINER_TYPES:
                order.append(str(comp.get("type")))
            for child in comp.get("children") or []:
                if isinstance(child, str):
                    walk(child)

        for child in index[container_id].get("children") or []:
            if isinstance(child, str):
                walk(child)
        return tuple(order)

    if all_containers:
        return [Screen(container_id=c, block_types=blocks_under(c)) for c in root_children]
    return [Screen(container_id=root, block_types=blocks_under(root))]


# --------------------------------------------------------------------------------------
# El checker: de un ui_spec (+ estado del render) a una lista de flags
# --------------------------------------------------------------------------------------

FLAG_LABELS: dict[str, str] = {
    "node_not_ready": "render no listo",
    "episode_declined": "episodio declinado",
    "status_fallback": "acabo en fallback",
    "passive_reveal": "reveal pasivo (esconde info tras clic)",
    "didact_glossary": "DidactGlossary (debe irse: Curio cubre definiciones)",
    "flashcard_as_closer": "Flashcard como cierre/evaluacion",
    "screen_overcrowded": "pantalla recargada (viola un-foco)",
    "missing_interaction": "pantalla sin interaccion",
    "assessment_not_varied": "evaluacion no variada (mismo tipo en todo el curso)",
}

FLAG_ORDER: tuple[str, ...] = tuple(FLAG_LABELS)


@dataclass
class Flag:
    code: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}" if self.detail else self.code


@dataclass
class NodeInspection:
    course: str
    node_id: str
    node_title: str
    status: str
    ui_spec: dict[str, Any] | None
    flags: list[Flag] = field(default_factory=list)
    #: El tipo con el que el nodo evalua/cierra, para la comprobacion de variedad.
    assessment_type: str | None = None

    @property
    def flag_codes(self) -> list[str]:
        return [f.code for f in self.flags]

    @property
    def clean(self) -> bool:
        return not self.flags


def _closer_and_assessment(block_types_all: list[str]) -> tuple[str | None, str | None]:
    """Devuelve (tipo del cierre, tipo de evaluacion real) del nodo entero.

    Cierre = ultimo bloque en orden de lectura. Evaluacion = ultimo bloque que reclama
    EVALUAR; si no hay, el ultimo elemento interactivo (que hace de evaluacion de facto).
    """
    closer = block_types_all[-1] if block_types_all else None
    assessment = next(
        (t for t in reversed(block_types_all) if t in ASSESSMENT_TYPES), None
    )
    if assessment is None:
        assessment = next(
            (t for t in reversed(block_types_all) if t in INTERACTIVE_TYPES), None
        )
    return closer, assessment


def inspect_node(
    node: NodeInspection, *, max_blocks: int = DEFAULT_MAX_BLOCKS
) -> NodeInspection:
    """Aplica todas las comprobaciones de nodo. No toca nada: solo rellena flags."""
    status = (node.status or "").lower()
    spec = node.ui_spec if isinstance(node.ui_spec, dict) else None

    # --- estado del render / episodio ---------------------------------------------
    if status == "fallback":
        node.flags.append(Flag("status_fallback", f"status={status}"))
    if status not in ("ready", "fallback"):
        node.flags.append(Flag("node_not_ready", f"status={status or 'sin fila'}"))

    generation = (spec or {}).get("generation") if spec else None
    if isinstance(generation, dict):
        episode_status = generation.get("episode_status")
        if episode_status == "declined":
            reason = generation.get("episode_decline_reason") or "sin motivo"
            node.flags.append(Flag("episode_declined", str(reason)))

    if spec is None:
        return node  # sin spec no hay pantallas que inspeccionar

    # --- inventario de tipos servidos ---------------------------------------------
    reachable = _reachable_ids(spec)
    index = _component_index(spec)
    types_present = [str(index[cid].get("type")) for cid in reachable if cid in index]
    non_container = [t for t in types_present if t not in CONTAINER_TYPES]

    # --- reveal pasivo (principio 1) ----------------------------------------------
    reveals = sorted({t for t in types_present if t in PASSIVE_REVEAL_TYPES})
    if reveals:
        node.flags.append(Flag("passive_reveal", ", ".join(reveals)))

    # --- DidactGlossary (debe desaparecer) ----------------------------------------
    if "DidactGlossary" in types_present:
        node.flags.append(Flag("didact_glossary", "presente"))

    # --- Flashcard como cierre/evaluacion (principio 4) ---------------------------
    closer, assessment = _closer_and_assessment(non_container)
    node.assessment_type = assessment
    if "Flashcard" in non_container:
        real_assessment = any(t in ASSESSMENT_TYPES for t in non_container)
        if closer == "Flashcard" or not real_assessment:
            why = "es el cierre" if closer == "Flashcard" else "unica interaccion evaluable"
            node.flags.append(Flag("flashcard_as_closer", why))

    # --- por pantalla: recargada / sin interaccion --------------------------------
    for i, screen in enumerate(screens_of(spec)):
        n_blocks = len(screen.block_types)
        if n_blocks > max_blocks:
            node.flags.append(
                Flag("screen_overcrowded", f"pantalla {i + 1}: {n_blocks} bloques > {max_blocks}")
            )
        if n_blocks and not any(t in INTERACTIVE_TYPES for t in screen.block_types):
            node.flags.append(
                Flag("missing_interaction", f"pantalla {i + 1}: solo contenido pasivo")
            )
    return node


def apply_course_checks(nodes: list[NodeInspection]) -> None:
    """Comprobaciones a nivel de curso (mutan las flags de los nodos afectados)."""
    by_course: dict[str, list[NodeInspection]] = collections.defaultdict(list)
    for node in nodes:
        by_course[node.course].append(node)

    for course, group in by_course.items():
        assessed = [n for n in group if n.assessment_type]
        kinds = {n.assessment_type for n in assessed}
        if len(assessed) >= 2 and len(kinds) == 1:
            only = next(iter(kinds))
            for node in assessed:
                node.flags.append(
                    Flag("assessment_not_varied", f"todo el curso evalua con {only}")
                )


# --------------------------------------------------------------------------------------
# Digest
# --------------------------------------------------------------------------------------


def build_digest(nodes: list[NodeInspection], *, mode: str, meta: dict[str, Any]) -> dict[str, Any]:
    by_course: dict[str, list[NodeInspection]] = collections.defaultdict(list)
    for node in nodes:
        by_course[node.course].append(node)

    per_category: collections.Counter[str] = collections.Counter()
    for node in nodes:
        for code in set(node.flag_codes):  # una vez por nodo y categoria
            per_category[code] += 1

    flagged = [n for n in nodes if not n.clean]
    courses_payload = []
    for course in sorted(by_course):
        group = by_course[course]
        courses_payload.append({
            "course": course,
            "nodes": len(group),
            "clean": sum(n.clean for n in group),
            "flagged": sum(not n.clean for n in group),
            "node_detail": [
                {
                    "node_id": n.node_id,
                    "title": n.node_title,
                    "status": n.status,
                    "assessment_type": n.assessment_type,
                    "flags": [str(f) for f in n.flags],
                }
                for n in group
            ],
        })

    return {
        "schema_version": 1,
        "mode": mode,
        "meta": meta,
        "totals": {
            "nodes": len(nodes),
            "clean": sum(n.clean for n in nodes),
            "flagged": len(flagged),
            "courses": len(by_course),
            "by_category": {code: per_category.get(code, 0) for code in FLAG_ORDER},
        },
        "courses": courses_payload,
    }


def print_digest(digest: dict[str, Any]) -> None:
    meta = digest.get("meta") or {}
    print()
    print("=" * 78)
    print(f"DIGEST DE CALIDAD DE LECCIONES  (modo: {digest['mode']})")
    for key, value in meta.items():
        print(f"  {key}: {value}")
    print("=" * 78)

    for course in digest["courses"]:
        print(f"\n[{course['course']}]  {course['nodes']} nodos  "
              f"({course['clean']} limpios / {course['flagged']} marcados)")
        for node in course["node_detail"]:
            title = (node["title"] or "")[:44]
            if node["flags"]:
                print(f"  x {title:<46} {node['status']}")
                for flag in node["flags"]:
                    print(f"       - {flag}")
            else:
                print(f"  . {title:<46} {node['status']}  (limpio)")

    totals = digest["totals"]
    print("\n" + "-" * 78)
    print(f"TOTAL: {totals['nodes']} nodos en {totals['courses']} cursos  |  "
          f"{totals['clean']} limpios, {totals['flagged']} marcados "
          f"({_pct(totals['clean'], totals['nodes'])}% limpios)")
    print("\nPor categoria (nodos afectados):")
    for code in FLAG_ORDER:
        count = totals["by_category"].get(code, 0)
        mark = "  " if count == 0 else "->"
        print(f"  {mark} {code:<22} {count:>4}   {FLAG_LABELS[code]}")
    print("-" * 78)


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


# --------------------------------------------------------------------------------------
# Fuente 1: Postgres (renders reales ya generados) - solo lectura via docker
# --------------------------------------------------------------------------------------


def _psql_json(sql: str, *, docker_service: str = "db") -> Any:
    """Ejecuta SQL que devuelve UNA columna JSON y la parsea. Solo lectura."""
    cmd = [
        "docker", "compose", "exec", "-T", docker_service, "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc ' + _shquote(sql),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PACKAGE_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"psql fallo ({proc.returncode}): {proc.stderr.strip()[:400]}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def _shquote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def load_from_db(
    *, course_hints: list[str], limit_courses: int, docker_service: str
) -> tuple[list[NodeInspection], dict[str, Any]]:
    """Carga cursos reales y el render mas reciente (preferentemente ready) por nodo."""
    if course_hints:
        conds = " OR ".join(
            f"c.title ILIKE {_shquote('%' + h + '%')}" for h in course_hints
        )
        course_filter = f"({conds})"
    else:
        course_filter = "TRUE"

    # Cursos dinamicos con al menos un render listo, con mas renders listos primero.
    course_sql = (
        "SELECT COALESCE(json_agg(t.id), '[]'::json) FROM ("
        "  SELECT c.id, count(r.id) FILTER (WHERE r.status='ready') AS ready"
        "  FROM courses c"
        "  JOIN course_nodes n ON n.course_id=c.id"
        "  LEFT JOIN node_renders r ON r.node_id=n.id"
        f"  WHERE c.delivery_mode='dynamic' AND {course_filter}"
        "  GROUP BY c.id"
        "  HAVING count(r.id) FILTER (WHERE r.status='ready') > 0"
        f"  ORDER BY ready DESC LIMIT {int(limit_courses)}"
        ") t"
    )
    course_ids = _psql_json(course_sql, docker_service=docker_service) or []
    if not course_ids:
        raise RuntimeError(
            "no hay cursos dinamicos con renders 'ready' que casen con el filtro."
        )
    id_list = ", ".join(f"'{cid}'" for cid in course_ids)

    node_sql = (
        "SELECT COALESCE(json_agg(row), '[]'::json) FROM ("
        "  SELECT json_build_object("
        "    'course', c.title, 'node_id', n.id::text, 'node_title', n.title,"
        "    'position', n.position, 'status', r.status, 'ui_spec', r.ui_spec"
        "  ) AS row"
        "  FROM courses c"
        "  JOIN course_nodes n ON n.course_id=c.id"
        "  LEFT JOIN LATERAL ("
        "    SELECT status, ui_spec FROM node_renders r2"
        "    WHERE r2.node_id=n.id AND r2.is_preview=false"
        "    ORDER BY (r2.status='ready') DESC, r2.created_at DESC LIMIT 1"
        "  ) r ON true"
        f"  WHERE c.id IN ({id_list})"
        "  ORDER BY c.title, n.position"
        ") s"
    )
    rows = _psql_json(node_sql, docker_service=docker_service) or []
    # Un nodo sin ninguna fila de render no es una leccion mala: es una leccion que aun
    # nadie ha generado (el aprendiz no ha llegado). Se cuenta aparte y no se puntua,
    # para que el digest hable solo de lecciones REALMENTE servidas.
    rendered = [r for r in rows if r.get("status")]
    not_rendered = len(rows) - len(rendered)
    nodes = [
        NodeInspection(
            course=row.get("course") or "?",
            node_id=str(row.get("node_id")),
            node_title=row.get("node_title") or "",
            status=str(row.get("status")),
            ui_spec=row.get("ui_spec") if isinstance(row.get("ui_spec"), dict) else None,
        )
        for row in rendered
    ]
    meta = {
        "fuente": "postgres (node_renders.ui_spec, solo lectura)",
        "cursos_seleccionados": len(course_ids),
        "filtro": course_hints or "(cursos con mas renders listos)",
        "nodos_sin_render_omitidos": not_rendered,
    }
    return nodes, meta


# --------------------------------------------------------------------------------------
# Fuente 2: el pipeline real (offline con fixtures, o en vivo con DeepSeek)
# --------------------------------------------------------------------------------------

#: Cuatro encargos del corpus de quality_bench que abarcan naturalezas distintas.
DEFAULT_PIPELINE_ENCARGOS = (
    "extintor",              # procedimiento (regla PAS)
    "alergenos-hosteleria",  # conocimiento/hechos (los 14 alergenos)
    "higiene-alimentaria",   # datos/comparacion (temperaturas -> chart)
    "prevencion-riesgos",    # habilidad fisica (manipulacion de cargas)
)


async def load_from_pipeline(
    *, encargo_names: list[str], offline: bool, repeat: int
) -> tuple[list[NodeInspection], dict[str, Any]]:
    """Genera cada encargo por el pipeline real y recoge su ui_spec servido.

    Reutiliza toda la maquinaria de quality_bench (sesion en memoria, costuras de SSE y
    proveedor, instrumentacion de nodos). El curso de cada encargo es su propio "curso"
    a efectos del digest, asi que la comprobacion de variedad de evaluacion se hace por
    encargo (que es como se sirve en produccion: un curso, sus nodos).
    """
    import quality_bench as qb
    from src.config import settings
    from src.core import sse

    encargos = [qb.CORPUS_BY_NAME[name] for name in encargo_names]

    # --- costuras, igual que en quality_bench.run_bench ---------------------------
    if offline:
        settings.LLM_MODEL = qb.OFFLINE_MODEL
        settings.LLM_RUNTIME_FAST_MODEL = qb.OFFLINE_MODEL
        settings.LLM_RUNTIME_HEAVY_MODEL = qb.OFFLINE_MODEL
        settings.EMBEDDING_MODEL = qb.OFFLINE_MODEL
        qb.install_offline_llm(_PACKAGE_ROOT / "bench_out" / "fixtures")
        qb.install_offline_prompt_capture()
    elif not settings.LLM_API_KEY:
        raise RuntimeError(
            "no hay LLM_API_KEY: usa --offline o pon la clave en apps/skillnet-api/.env"
        )
    else:
        qb.install_provider_shim(qb.ProviderStats(), user_agent=qb.BENCH_USER_AGENT)
        qb.install_prompt_capture()

    collector = qb.SseCollector()
    sse.publish = collector.publish  # type: ignore[assignment]
    sse.wait_for_subscriber = collector.wait_for_subscriber  # type: ignore[assignment]
    qb.install_node_instrumentation()

    from src.agents.runtime.router import tier_config

    nodes: list[NodeInspection] = []
    prices = dict(qb.PRICES)
    for encargo in encargos:
        for rep in range(1, repeat + 1):
            run, _recorder = await qb.run_one(
                encargo, rep, arm="raw", offline=offline, prices=prices
            )
            title = encargo.title if repeat == 1 else f"{encargo.title} (pase {rep})"
            nodes.append(
                NodeInspection(
                    course=f"Curso: {encargo.title}",
                    node_id=f"{encargo.name}-r{rep}",
                    node_title=title,
                    status=run.render_status,
                    ui_spec=run.ui_spec,
                )
            )
            if not offline:
                await asyncio.sleep(1.0)  # el plan gratuito da 429 con facilidad

    meta = {
        "fuente": f"pipeline real ({'offline/fixtures' if offline else 'en vivo/DeepSeek'})",
        "modelo_fast": tier_config({}, "fast").model,
        "modelo_heavy": tier_config({}, "heavy").model,
        "encargos": encargo_names,
        "pases": repeat,
    }
    return nodes, meta


# --------------------------------------------------------------------------------------
# Autocomprobacion: specs sinteticos con defectos conocidos
# --------------------------------------------------------------------------------------


def _comp(cid: str, ctype: str, children: list[str] | None = None, **props: Any) -> dict:
    return {"id": cid, "type": ctype, "props": props, "children": children or []}


def _spec(root: str, components: list[dict], *, generation: dict | None = None) -> dict:
    out: dict[str, Any] = {
        "version": "skillnet-ui/1", "format": "mixed", "root": root, "components": components,
    }
    if generation is not None:
        out["generation"] = generation
    return out


def _self_test_fixtures() -> list[tuple[str, NodeInspection, set[str]]]:
    """(nombre, nodo, flags que DEBEN salir). Cada fixture aisla una comprobacion."""
    fixtures: list[tuple[str, NodeInspection, set[str]]] = []

    # 1) Limpio: contenido + una interaccion real de cierre, un solo foco.
    clean = _spec("root", [
        _comp("root", "Stack", ["lead", "steps", "q1"]),
        _comp("lead", "TextContent", text="Para resolverlo tu.", variant="lead"),
        _comp("steps", "StepSequence", title="Como", steps=["a", "b", "c"]),
        _comp("q1", "QuizItem", item_id="q1", item_type="test", question="?", options=["a", "b"]),
    ], generation={"episode_status": "ready", "shell_mode": "episode"})
    fixtures.append(("limpio", NodeInspection("C", "n1", "limpio", "ready", clean), set()))

    # 2) DidactGlossary + reveal pasivo (HintReveal).
    glossary = _spec("root", [
        _comp("root", "Stack", ["g", "h", "q"]),
        _comp("g", "DidactGlossary", title="T", terms=["x"], definitions=["y"]),
        _comp("h", "HintReveal", title="pista", hints=["p1"], solution="s"),
        _comp("q", "QuizItem", item_id="q1", item_type="test", question="?", options=["a", "b"]),
    ])
    fixtures.append((
        "glosario+reveal",
        NodeInspection("C", "n2", "glosario", "ready", glossary),
        {"didact_glossary", "passive_reveal"},
    ))

    # 3) Sin interaccion: solo contenido pasivo.
    passive = _spec("root", [
        _comp("root", "Stack", ["t1", "t2", "call"]),
        _comp("t1", "TextContent", text="a", variant="lead"),
        _comp("t2", "TextContent", text="b", variant="body"),
        _comp("call", "Callout", tone="warn", text="ojo"),
    ])
    fixtures.append((
        "sin-interaccion",
        NodeInspection("C", "n3", "pasivo", "ready", passive),
        {"missing_interaction"},
    ))

    # 4) Pantalla recargada: 8 bloques de contenido en un foco.
    crowded = _spec("root", [
        _comp("root", "Stack", [f"b{i}" for i in range(8)] + ["q"]),
        *[_comp(f"b{i}", "TextContent", text=str(i), variant="body") for i in range(8)],
        _comp("q", "QuizItem", item_id="q1", item_type="test", question="?", options=["a", "b"]),
    ])
    fixtures.append((
        "recargada",
        NodeInspection("C", "n4", "recargada", "ready", crowded),
        {"screen_overcrowded"},
    ))

    # 5) Flashcard como cierre, sin evaluacion real.
    flash = _spec("root", [
        _comp("root", "Stack", ["lead", "fc"]),
        _comp("lead", "TextContent", text="idea", variant="lead"),
        _comp("fc", "Flashcard", front="pregunta", back="respuesta"),
    ])
    fixtures.append((
        "flashcard-cierre",
        NodeInspection("C", "n5", "flash", "ready", flash),
        {"flashcard_as_closer"},
    ))

    # 6) Episodio declinado + status fallback.
    declined = _spec("root", [
        _comp("root", "Stack", ["m"]),
        _comp("m", "Markdown", content="leccion semilla"),
    ], generation={"episode_status": "declined",
                   "episode_decline_reason": "missing_knowledge_pack"})
    fixtures.append((
        "declinado",
        NodeInspection("C", "n6", "declinado", "fallback", declined),
        {"episode_declined", "status_fallback", "missing_interaction"},
    ))

    # 7) Render no listo (failed, sin spec).
    fixtures.append((
        "no-listo",
        NodeInspection("C", "n7", "fallido", "failed", None),
        {"node_not_ready"},
    ))
    return fixtures


def run_self_test(*, max_blocks: int) -> int:
    print("Autocomprobacion del checker de rubrica")
    print("=" * 60)
    fixtures = _self_test_fixtures()
    ok = True

    # --- fixtures de nodo aislados -------------------------------------------------
    for name, node, expected in fixtures:
        inspect_node(node, max_blocks=max_blocks)
        got = set(node.flag_codes)
        # Los fixtures declaran los flags que DEBEN salir; no deben salir otros de nodo.
        node_flag_codes = set(FLAG_ORDER) - {"assessment_not_varied"}
        unexpected = (got & node_flag_codes) - expected
        missing = expected - got
        status = "OK" if not missing and not unexpected else "FALLO"
        ok = ok and not missing and not unexpected
        print(f"  [{status}] {name:<20} esperado={sorted(expected)} obtenido={sorted(got)}")
        if missing:
            print(f"           faltan: {sorted(missing)}")
        if unexpected:
            print(f"           sobran: {sorted(unexpected)}")

    # --- comprobacion de curso: evaluacion no variada ------------------------------
    def quiz_node(nid: str) -> NodeInspection:
        spec = _spec("root", [
            _comp("root", "Stack", ["lead", "q"]),
            _comp("lead", "TextContent", text="x", variant="lead"),
            _comp("q", "QuizItem", item_id=nid, item_type="test", question="?", options=["a", "b"]),
        ])
        return NodeInspection("CursoMonotono", nid, nid, "ready", spec)

    mono = [quiz_node("a"), quiz_node("b"), quiz_node("c")]
    for n in mono:
        inspect_node(n, max_blocks=max_blocks)
    apply_course_checks(mono)
    variety_ok = all("assessment_not_varied" in n.flag_codes for n in mono)
    ok = ok and variety_ok
    print(f"  [{'OK' if variety_ok else 'FALLO'}] {'evaluacion-no-variada':<20} "
          f"3 nodos con QuizItem -> flag en {sum('assessment_not_varied' in n.flag_codes for n in mono)}/3")

    # curso variado NO debe marcarse
    def drag_node(nid: str) -> NodeInspection:
        spec = _spec("root", [
            _comp("root", "Stack", ["lead", "d"]),
            _comp("lead", "TextContent", text="x", variant="lead"),
            _comp("d", "DragOrder", instruction="ordena", items=["a", "b"], correctOrder=["a", "b"]),
        ])
        return NodeInspection("CursoVariado", nid, nid, "ready", spec)

    varied = [quiz_node("a"), drag_node("b")]
    for n in varied:
        inspect_node(n, max_blocks=max_blocks)
    apply_course_checks(varied)
    no_false = not any("assessment_not_varied" in n.flag_codes for n in varied)
    ok = ok and no_false
    print(f"  [{'OK' if no_false else 'FALLO'}] {'variedad-sin-falso':<20} "
          f"curso con QuizItem+DragOrder -> sin flag de variedad")

    print("=" * 60)
    print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lesson_quality_bench",
        description=(
            "Marca violaciones de la rubrica de calidad de leccion sobre los ui_spec "
            "servidos y saca un digest medible. Solo lectura sobre src/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--self-test", action="store_true",
                     help="Corre los fixtures sinteticos y verifica que cada flag salta.")
    src.add_argument("--db", action="store_true",
                     help="Inspecciona renders reales de Postgres (solo lectura, en vivo).")
    src.add_argument("--pipeline", action="store_true",
                     help="Genera nodos por el pipeline real y los inspecciona.")

    parser.add_argument("--offline", action="store_true",
                        help="Con --pipeline: usa FixtureLLMService (sin clave, sin red).")
    parser.add_argument("--only", action="append", default=[],
                        help="Con --pipeline: solo estos encargos (repetible o separado por comas).")
    parser.add_argument("--repeat", type=int, default=1,
                        help="Con --pipeline: pases por encargo.")
    parser.add_argument("--course", action="append", default=[],
                        help="Con --db: filtra cursos cuyo titulo contenga esto (repetible).")
    parser.add_argument("--limit-courses", type=int, default=6,
                        help="Con --db: cuantos cursos como maximo (los de mas renders listos).")
    parser.add_argument("--docker-service", default="db",
                        help="Con --db: nombre del servicio de Postgres en docker compose.")
    parser.add_argument("--max-blocks", type=int, default=DEFAULT_MAX_BLOCKS,
                        help="Bloques por pantalla antes de marcar 'recargada'.")
    parser.add_argument("--json", type=Path, default=None,
                        help="Guarda el digest completo en este fichero JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    for warning in verify_catalog():
        print(f"[aviso] {warning}", file=sys.stderr)

    if args.self_test or not (args.db or args.pipeline):
        if not args.self_test and not (args.db or args.pipeline):
            print("(sin modo elegido: corriendo --self-test; usa --db o --pipeline para medir)\n")
        return run_self_test(max_blocks=args.max_blocks)

    if args.db:
        nodes, meta = load_from_db(
            course_hints=[h.strip() for c in args.course for h in c.split(",") if h.strip()],
            limit_courses=args.limit_courses,
            docker_service=args.docker_service,
        )
        mode = "db"
    else:
        only: list[str] = []
        for entry in args.only:
            only.extend(p.strip() for p in entry.split(",") if p.strip())
        names = only or list(DEFAULT_PIPELINE_ENCARGOS)
        nodes, meta = asyncio.run(
            load_from_pipeline(encargo_names=names, offline=args.offline, repeat=args.repeat)
        )
        mode = "pipeline-offline" if args.offline else "pipeline-live"

    for node in nodes:
        inspect_node(node, max_blocks=args.max_blocks)
    apply_course_checks(nodes)

    digest = build_digest(nodes, mode=mode, meta=meta)
    print_digest(digest)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nDigest guardado en {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
