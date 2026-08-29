"""Donde se busca `.env`, y por que no puede depender de donde estes parado.

`env_file=".env"` se resolvia contra el CWD. Lanzado desde `apps/skillnet-api`, que es
justo lo que documenta `scripts/quality_bench.py`, no encontraba el `.env` de la raiz y
TODOS los flags caian a su valor por defecto — en silencio, porque un fichero de entorno
ausente no es un error. El banco construyo asi un grafo distinto del que sirve el producto
durante 91 renders (2026-08-22 a 2026-08-28).

El primer arreglo indexaba `parents[3]` para la raiz del repo. Correcto en el checkout
(`apps/skillnet-api/src/config.py`), `IndexError` en la imagen, donde el paquete se copia a
`/app` y solo hay tres ancestros. Uvicorn no arrancaba. De ahi que estos tests prueben la
funcion pura a las dos profundidades en vez de fiarse de la que resulte tener el repo.
"""

from __future__ import annotations

from pathlib import Path

from src.config import _env_file_candidates


def test_a_shallow_layout_does_not_raise() -> None:
    """El layout de la imagen: `/app/src/config.py`, tres ancestros contando la raiz.

    Las expectativas se derivan de `resolve()` en vez de escribirse literales: en Windows
    `resolve()` antepone la letra de unidad, y un test que compara contra `/app/.env` falla
    por la plataforma en vez de por el comportamiento.
    """
    module = Path("/app/src/config.py")
    candidates = _env_file_candidates(module)
    assert candidates, "una ruta corta tiene que producir algun candidato"
    assert candidates[-1] == module.resolve().parents[1] / ".env"


def test_the_closest_ancestor_wins() -> None:
    """pydantic-settings da precedencia al ULTIMO fichero, asi que el mas cercano va al final.

    Un `.env` junto al paquete tiene que poder pisar al de la raiz del repo; si el orden se
    invierte, la configuracion local deja de mandar sin que nada falle.
    """
    module = Path("/repo/apps/skillnet-api/src/config.py")
    resolved = module.resolve()
    candidates = _env_file_candidates(module)
    assert candidates[-1] == resolved.parents[1] / ".env"
    assert candidates[0] == resolved.parents[3] / ".env"


def test_the_real_module_resolves_without_raising() -> None:
    """Lo que hacia caer al contenedor era la evaluacion en tiempo de import."""
    from src import config

    assert config._ENV_FILES
    assert all(candidate.name == ".env" for candidate in config._ENV_FILES)
