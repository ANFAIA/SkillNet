"""El chequeo de dimensiones, que existe porque el fallo que detecta es invisible.

Sin el: `EMBEDDING_DIMENSIONS` no cuadra con la columna, Postgres rechaza la insercion, y
el rechazo cae dentro del `except Exception` de `src/services/ingestion.py`, que lo
registra como "embedding unavailable", guarda `full_text` y marca el documento **READY**.
Queda un documento aparentemente correcto que no se puede recuperar por RAG.

Todo aqui es unitario: `EmbeddingCheck` es un dataclass sobre dos enteros, asi que los
casos se construyen a mano sin base de datos.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.services.embedding_check import EmbeddingCheck


class TestStatus:
    def test_coincidir_es_ok(self):
        assert EmbeddingCheck(configured=768, column=768).status == "ok"

    def test_no_coincidir_es_mismatch(self):
        assert EmbeddingCheck(configured=384, column=768).status == "mismatch"

    def test_columna_sin_restringir_se_distingue_de_un_desajuste(self):
        """`vector` sin dimension funciona, pero deja de validar: no es ni ok ni error."""
        assert EmbeddingCheck(configured=768, column=None).status == "unconstrained"


class TestDetail:
    def test_cuando_cuadra_no_hay_nada_que_decir(self):
        assert EmbeddingCheck(configured=768, column=768).detail is None

    def test_el_desajuste_nombra_los_dos_numeros(self):
        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "384" in detail
        assert "vector(768)" in detail

    def test_el_desajuste_avisa_de_que_el_fallo_es_invisible(self):
        """Lo que hace el mensaje util: sin esto nadie sabe que hay que mirar."""
        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "sin error visible" in detail

    def test_con_un_modelo_recortable_el_arreglo_es_una_linea_del_env(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """`text-embedding-3-*` acepta `dimensions`, asi que no hay que migrar."""
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")

        detail = EmbeddingCheck(configured=1536, column=768).detail

        assert detail is not None
        assert "EMBEDDING_DIMENSIONS=768" in detail
        assert "migra" not in detail

    def test_con_un_modelo_de_dimension_fija_el_arreglo_es_migrar(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """No prometer un arreglo facil cuando el modelo no puede recortar."""
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "multilingual-e5-small")

        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "migra la columna" in detail
        assert "reingiere" in detail

    def test_la_columna_sin_restringir_explica_que_esperabamos(self):
        detail = EmbeddingCheck(configured=768, column=None).detail

        assert detail is not None
        assert "vector(768)" in detail
        assert "0008" in detail


class TestDimensionsParameter:
    """`(c)`: pedir la dimension al proveedor es lo que hace cierto "una clave y ya"."""

    def _service(self, model: str):
        from src.llm.embedding import EmbeddingConfig, EmbeddingService

        return EmbeddingService(
            EmbeddingConfig(model=model, api_base=None, api_key="k", dimensions=768)
        )

    def test_se_envia_a_text_embedding_3(self):
        """Sale 1536 de fabrica; sin pedir 768 no entra en la columna."""
        kwargs = self._service("text-embedding-3-small")._kwargs(["hola"])

        assert kwargs["dimensions"] == 768

    def test_tambien_a_la_variante_large(self):
        kwargs = self._service("text-embedding-3-large")._kwargs(["hola"])

        assert kwargs["dimensions"] == 768

    def test_no_se_envia_a_un_proveedor_que_no_lo_conoce(self):
        """Mandarlo donde no se soporta es un error, no una pista ignorada."""
        for model in ("ollama/paraphrase-multilingual", "multilingual-e5-base"):
            assert "dimensions" not in self._service(model)._kwargs(["hola"])
