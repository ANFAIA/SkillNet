"""document_chunks.embedding a la dimension configurada, e indice HNSW

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04

Dos cambios en la misma migracion porque los dos obligan a rehacer el indice, y
partirlos en dos costaria dos reconstrucciones del mismo indice sobre la misma tabla.

## La dimension, y por que va fijada aqui

Cambiar de proveedor de embeddings cambia la dimension del vector, y no hay conversion
posible: un vector de 384 componentes y otro de 768 no describen el mismo espacio, asi
que no se pueden castear, ni truncar, ni rellenar. La columna se **recrea** y los
chunks se vuelven a ingerir. Eso es honesto: al cambiar de modelo todo embedding
guardado deja de valer igualmente, y fingir una migracion de datos solo dejaria
vectores del modelo viejo indistinguibles de los nuevos.

``0001_initial.py`` escribio ``Vector(settings.EMBEDDING_DIMENSIONS)``, es decir dejo
que una variable de entorno decidiera el esquema. **Aqui no se repite, y no por
gusto: se probo y rompio.** La primera version de esta migracion leia el ajuste, y
lanzar la suite de integracion basto para corromper la base: ``test_migration_0005``
hace upgrade -> downgrade -> upgrade, el downgrade paso por aqui, y el upgrade
siguiente releyo ``EMBEDDING_DIMENSIONS`` — que en un pytest del host vale el default
porque ``SettingsConfigDict(env_file=".env")`` resuelve relativo al directorio del
proceso y nunca ve el ``.env`` de la raiz que lee docker-compose. Resultado: columna
de vuelta a 384, los 17 chunks del corpus borrados, y ni un test en rojo avisando.

Un esquema que depende del entorno tampoco se puede razonar: ``alembic current`` deja
de bastar para saber que hay en la base, y un volcado de produccion no entra en un
desarrollo configurado distinto.

Asi que la dimension la manda **el esquema**, y el modelo se adapta. Es la direccion
correcta de la dependencia y es como funciona cualquier despliegue vectorial de
verdad: no se cambia la dimension de los embeddings editando una variable de entorno.
El default de ``EMBEDDING_DIMENSIONS`` en ``src/config.py`` se sube a 768 en el mismo
commit para que coincida, junto con el modelo por defecto — ``multilingual-e5-base``,
768 dims, misma familia que el anterior asi que la logica de prefijos ``query:`` /
``passage:`` sigue aplicando.

## El indice

``0001_initial`` creo ``ivfflat ... WITH (lists = 10)``. IVFFlat particiona el espacio
en listas y solo mira unas pocas por consulta, asi que su recall depende de que
``lists`` este dimensionado al numero de filas (la regla habitual es ``filas/1000``) y
de que el indice se haya construido **sobre datos representativos**: sobre una tabla
casi vacia los centroides no significan nada. Con 17 filas, `lists = 10` no es una
eleccion sino un accidente.

HNSW no se entrena: construye un grafo navegable incremental, da mejor recall a
igualdad de latencia en corpus pequenos y medianos, y no hay ningun parametro que haya
que reajustar cada vez que la tabla crece un orden de magnitud. A cambio ocupa mas y
se construye mas despacio, que es el intercambio correcto para una tabla que se lee en
cada pregunta y se escribe solo al ingerir un documento.

``vector_cosine_ops`` se mantiene: ``similarity_search`` ordena por
``cosine_distance``, y un indice con otra clase de operador simplemente no se usaria.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Literales, nunca `settings`. Ver el docstring: leerlo del entorno hizo que la propia
#: suite de tests revirtiera el esquema y borrara el corpus sin un solo fallo en rojo.
_DIMENSIONS = 768
_OLD_DIMENSIONS = 384
_INDEX = "idx_chunks_embedding"


def _swap_embedding_column(dimensions: int, index_sql: str) -> None:
    """Vaciar los chunks, recrear la columna a ``dimensions``, y rehacer el indice.

    **Se borran los chunks, no se conservan con embedding NULL.** La columna es
    ``NOT NULL`` en ``DocumentChunk``, asi que dejar filas vacias obligaria a relajar el
    modelo; pero sobre todo, un chunk con embedding NULL sigue saliendo de
    ``similarity_search`` — ``cosine_distance`` sobre NULL da NULL y ordena al final —
    de modo que la busqueda devolveria filas sin vector como si fueran resultados. Vale
    mas no tenerlos.

    Perderlos no rompe nada mientras se reingiere: un documento con ``full_text`` y sin
    chunks es un estado legitimo que la escalera de ``src/services/retrieval.py`` ya
    contempla, y cae al peldano lexico o al documento completo.
    """
    op.execute(f"DROP INDEX IF EXISTS {_INDEX};")
    op.execute("DELETE FROM document_chunks;")
    op.drop_column("document_chunks", "embedding")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(dimensions), nullable=False),
    )
    op.execute(index_sql)


def upgrade() -> None:
    _swap_embedding_column(
        _DIMENSIONS,
        f"CREATE INDEX {_INDEX} ON document_chunks USING hnsw (embedding vector_cosine_ops);",
    )


def downgrade() -> None:
    _swap_embedding_column(
        _OLD_DIMENSIONS,
        f"CREATE INDEX {_INDEX} ON document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);",
    )
