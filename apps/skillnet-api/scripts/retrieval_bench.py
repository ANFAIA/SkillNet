#!/usr/bin/env python
"""Banco de calidad de la **recuperacion** (RAG, `src/services/retrieval.py`).

Para que sirve
==============

`quality_bench.py` mide lo que el modelo *escribe*. Esto mide lo que el modelo
*recibe*, que es la mitad que no estaba medida: hasta ahora la unica forma de saber si
un cambio en el RAG mejoraba algo era leer respuestas y opinar.

Y sin medida se creen cosas falsas. La primera ejecucion de este banco puso numero a
algo que llevaba tiempo pareciendo que funcionaba: con `EMBEDDING_MODEL=fixture/local`
el peldano vectorial acierta **cero** de 25, porque `FixtureEmbeddingService` mete
cada texto en un vector unitario aleatorio y consulta y pasaje quedan ortogonales.

    # contra el Postgres del docker-compose
    uv run python scripts/retrieval_bench.py

    # solo un recuperador, o solo un caso
    uv run python scripts/retrieval_bench.py --solo fts
    uv run python scripts/retrieval_bench.py --caso alergenos-14

    # detalle por caso, con lo que devolvio cada uno
    uv run python scripts/retrieval_bench.py --verbose

Es un **script, no un test**: el nombre no casa con `test_*.py`. Necesita el Postgres
sembrado con `seed_demo_v2`, que es un estado que una suite no puede exigir. Los tests
de `tests/integration/test_retrieval_fts.py` cubren el contrato; esto mide la calidad.

Que se mide
===========

Los tres recuperadores por separado, sobre las mismas 25 preguntas, mas la escalera
completa para ver **que peldano se activa de verdad**:

* `vector`   — `similarity_search` con el embedder configurado.
* `fts`      — `search_chunks_fts`, la busqueda lexica espanola.
* `escalera` — `ground_question`, que es lo que corre en produccion.

Metricas, todas a nivel de **seccion** y no de documento, porque acertar el documento
es facil con tres documentos y no distingue nada:

* **recall@5** — la seccion esperada esta entre los 5 primeros.
* **MRR**      — 1/posicion de la primera seccion correcta. Castiga acertar en 5º.
* **P@1**      — la primera es la correcta. Es la que nota el lector.
* **doc@1**    — el documento de la primera es el correcto. Piso, no objetivo.

**Por que la escalera saca peor MRR y P@1 que `fts` con el mismo recall.** No es una
regresion, es que se mide otra cosa. `assemble_context` numera los `[Fuente N]` del
bloque de contexto y construye la lista de citas en el mismo orden, y ese orden lo
decide `order_chunks`: por documento y posicion dentro del documento, para que el
contexto se lea como un texto seguido y no como un ranking. Los cinco pasajes estan
igualmente en el prompt — de ahi que recall@5 coincida — pero el primero de la lista
es el que aparece antes en el documento, no el mas relevante. Las dos ordenaciones no
se pueden separar sin desalinear los marcadores de sus citas.

Asi que **recall@5 es la metrica de calidad de recuperacion**; el MRR de `fts` mide
el ranking del recuperador, y el de `escalera` mide el orden narrativo. Compararlos
entre si no dice nada.

Las preguntas estan escritas con las palabras que usaria un empleado, no copiando el
heading: media docena llevan acentos que el corpus no tiene (`alergica`, `codigo`), y
varias evitan a proposito el termino exacto del titulo de la seccion.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.config import settings  # noqa: E402
from src.deps.db import async_session_factory, engine  # noqa: E402
from src.llm.embedding import resolve_embedding_config  # noqa: E402
from src.llm.fixtures import maybe_fixture_embedder  # noqa: E402
from src.models import Organization  # noqa: E402
from src.repositories.document_chunk_repo import DocumentChunkRepository  # noqa: E402
from src.services.retrieval import (  # noqa: E402
    SIMILARITY_FLOOR,
    ground_question,
    query_terms,
    usable_chunks,
)

ALERGENOS = "Manual de alergenos e informacion al cliente"
SALA = "Protocolo de sala: de la comanda al cobro"
CAJA = "Manejo de caja y arqueo diario"

TOP_K = 5


@dataclass(frozen=True)
class Caso:
    slug: str
    pregunta: str
    documento: str
    seccion: str


#: 25 preguntas. La columna `seccion` es la unica respuesta correcta a nivel de seccion.
CASOS: tuple[Caso, ...] = (
    # ── Alergenos ────────────────────────────────────────────────────────────────
    Caso("alergenos-14", "Cuantos alergenos hay que declarar por ley?", ALERGENOS,
         "Los catorce alergenos de declaracion obligatoria"),
    Caso("alergenos-lista", "Que alimentos entran en la lista de declaracion obligatoria?",
         ALERGENOS, "Los catorce alergenos de declaracion obligatoria"),
    Caso("alergenos-ley", "Que normativa nos obliga a informar de los alergenos?", ALERGENOS,
         "Marco legal"),
    Caso("alergenos-multa", "Nos pueden sancionar si no informamos?", ALERGENOS, "Marco legal"),
    Caso("alergenos-decir", "Como le digo a un cliente lo que lleva un producto?", ALERGENOS,
         "Como se informa al cliente"),
    Caso("alergenos-carta", "Hay que poner los alergenos por escrito en la carta?", ALERGENOS,
         "Como se informa al cliente"),
    Caso("alergenos-cruzada", "Que es la contaminacion cruzada?", ALERGENOS,
         "Contaminacion cruzada en el obrador"),
    Caso("alergenos-utensilios", "Puedo usar la misma pala para el pan sin gluten?", ALERGENOS,
         "Contaminacion cruzada en el obrador"),
    Caso("alergenos-reaccion", "Que hago si a alguien le da una reacción alérgica?", ALERGENOS,
         "Que hacer ante una reaccion alergica"),
    Caso("alergenos-emergencia", "A quien aviso si un cliente se pone malo por un alergeno?",
         ALERGENOS, "Que hacer ante una reaccion alergica"),
    # ── Sala ─────────────────────────────────────────────────────────────────────
    Caso("sala-apertura", "Que tengo que preparar antes de abrir el turno?", SALA,
         "Apertura del turno"),
    Caso("sala-recibir", "Como recibo a un cliente que acaba de entrar?", SALA,
         "Recepcion y acomodo del cliente"),
    Caso("sala-tpv", "Como meto la comanda en el TPV?", SALA, "Toma de comanda en el TPV"),
    Caso("sala-cocina", "Como me coordino con cocina para los tiempos?", SALA,
         "Coordinacion con cocina y tiempos"),
    Caso("sala-seguimiento", "Cada cuanto paso por las mesas mientras comen?", SALA,
         "Servicio en mesa y seguimiento"),
    Caso("sala-cobrar", "Como cierro la mesa cuando piden la cuenta?", SALA,
         "Cobro y cierre de mesa"),
    Caso("sala-queja", "Que hago si un cliente se queja de un plato?", SALA,
         "Incidencias y quejas"),
    Caso("sala-cierre", "Que hay que dejar hecho al cerrar el turno de sala?", SALA,
         "Cierre del turno"),
    # ── Caja ─────────────────────────────────────────────────────────────────────
    Caso("caja-fondo", "Cuanto efectivo se deja de fondo en el cajon?", CAJA, "Fondo de caja"),
    Caso("caja-tarjeta", "Se puede cobrar con tarjeta o solo en efectivo?", CAJA,
         "Cobros y medios de pago"),
    Caso("caja-arqueo", "Como se hace el arqueo al cerrar?", CAJA, "Arqueo de cierre"),
    Caso("caja-tpv", "Con que se compara el efectivo contado al cerrar?", CAJA,
         "Arqueo de cierre"),
    Caso("caja-descuadre", "Que hago si al contar no me cuadra el dinero?", CAJA, "Descuadres"),
    Caso("caja-falta", "A quien aviso si falta dinero en la caja?", CAJA, "Descuadres"),
    Caso("caja-cierre-turno", "Como dejo la caja preparada para el turno siguiente?", CAJA,
         "Fondo de caja"),
)


@dataclass
class Resultado:
    """Lo que un recuperador devolvio para un caso, ya evaluado."""

    caso: Caso
    posicion: int | None  # 1-indexed; None = no aparece en el top-k
    doc_primero: str | None
    devueltos: list[str]
    peldano: str | None = None

    @property
    def acierta_5(self) -> bool:
        return self.posicion is not None

    @property
    def rr(self) -> float:
        return 1.0 / self.posicion if self.posicion else 0.0

    @property
    def p_1(self) -> bool:
        return self.posicion == 1

    @property
    def doc_1(self) -> bool:
        return self.doc_primero == self.caso.documento


def _evaluar(caso: Caso, filas: list[dict], peldano: str | None = None) -> Resultado:
    headings = [(fila.get("metadata") or {}).get("heading", "") for fila in filas]
    docs = [fila.get("document_title") for fila in filas]
    posicion = next(
        (i for i, heading in enumerate(headings, 1) if heading == caso.seccion), None
    )
    return Resultado(
        caso=caso,
        posicion=posicion,
        doc_primero=docs[0] if docs else None,
        devueltos=[h for h in headings if h],
        peldano=peldano,
    )


async def _org_id(db) -> object:
    org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
    if org is None:
        sys.exit("No hay ninguna organizacion. Lanza `python -m src.seed_demo_v2` primero.")
    return org.id


async def _correr(casos: tuple[Caso, ...], solo: str | None) -> dict[str, list[Resultado]]:
    embedder = maybe_fixture_embedder(resolve_embedding_config({}))
    salida: dict[str, list[Resultado]] = {"vector": [], "fts": [], "escalera": []}

    async with async_session_factory() as db:
        org_id = await _org_id(db)
        repo = DocumentChunkRepository(db)

        for caso in casos:
            if solo in (None, "vector"):
                vector = await embedder.embed_query(caso.pregunta)
                filas = await repo.similarity_search(
                    org_id=org_id, query_embedding=vector, top_k=TOP_K
                )
                # El floor es parte del recuperador: sin el, "acierta" por azar.
                salida["vector"].append(_evaluar(caso, usable_chunks(filas)))

            if solo in (None, "fts"):
                filas = await repo.search_chunks_fts(
                    org_id=org_id, terms=sorted(query_terms(caso.pregunta)), top_k=TOP_K
                )
                salida["fts"].append(_evaluar(caso, filas))

            if solo in (None, "escalera"):
                grounded = await ground_question(
                    db,
                    user_id=org_id,  # sin matriculas: el peldano 3 no puede rescatar nada
                    org_id=org_id,
                    embedding_service=embedder,
                    query=caso.pregunta,
                    top_k=TOP_K,
                    whole_documents="org",
                )
                filas = [
                    {
                        "metadata": {"heading": cita.get("section", "")},
                        "document_title": cita.get("document"),
                    }
                    for cita in grounded.citations
                ]
                salida["escalera"].append(_evaluar(caso, filas, grounded.grounding))

    return {nombre: res for nombre, res in salida.items() if res}


def _tabla(resultados: dict[str, list[Resultado]]) -> None:
    cabecera = f"{'recuperador':<12} {'recall@5':>9} {'MRR':>7} {'P@1':>7} {'doc@1':>7}"
    print(cabecera)
    print("-" * len(cabecera))
    for nombre, res in resultados.items():
        total = len(res)
        print(
            f"{nombre:<12} "
            f"{sum(r.acierta_5 for r in res) / total * 100:>8.0f}% "
            f"{sum(r.rr for r in res) / total:>7.3f} "
            f"{sum(r.p_1 for r in res) / total * 100:>6.0f}% "
            f"{sum(r.doc_1 for r in res) / total * 100:>6.0f}%"
        )


def _peldanos(res: list[Resultado]) -> None:
    reparto: dict[str, int] = {}
    for resultado in res:
        reparto[resultado.peldano or "?"] = reparto.get(resultado.peldano or "?", 0) + 1
    print("\nPeldano que se activa (lo que corre en produccion):")
    for peldano, veces in sorted(reparto.items(), key=lambda kv: -kv[1]):
        print(f"  {peldano:<12} {veces:>3} / {len(res)}")


def _fallos(nombre: str, res: list[Resultado]) -> None:
    fallos = [r for r in res if not r.acierta_5]
    if not fallos:
        print(f"\n{nombre}: ningun fallo.")
        return
    print(f"\n{nombre}: {len(fallos)} sin la seccion correcta en el top {TOP_K}")
    for resultado in fallos:
        print(f"  [{resultado.caso.slug}] {resultado.caso.pregunta}")
        print(f"      esperada : {resultado.caso.seccion}")
        print(f"      devuelto : {' | '.join(resultado.devueltos) or '(nada)'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Banco de calidad de la recuperacion (RAG).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--solo",
        choices=["vector", "fts", "escalera"],
        help="Medir un solo recuperador.",
    )
    parser.add_argument("--caso", help="Medir un solo caso, por slug.")
    parser.add_argument(
        "--verbose", action="store_true", help="Volcar los fallos de cada recuperador."
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    casos = CASOS
    if args.caso:
        casos = tuple(c for c in CASOS if c.slug == args.caso)
        if not casos:
            print(f"No hay ningun caso con slug {args.caso!r}. Disponibles:")
            print("  " + "\n  ".join(c.slug for c in CASOS))
            return 2

    print(f"embedder         : {settings.EMBEDDING_MODEL}")
    print(f"SIMILARITY_FLOOR : {SIMILARITY_FLOOR}")
    print(f"casos            : {len(casos)}   top_k: {TOP_K}\n")

    resultados = await _correr(casos, args.solo)
    _tabla(resultados)
    if "escalera" in resultados:
        _peldanos(resultados["escalera"])
    if args.verbose:
        for nombre, res in resultados.items():
            _fallos(nombre, res)
    await engine.dispose()
    return 0


def main() -> int:
    return asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
