"""The dimension check, which exists because the failure it catches is invisible.

Without it: `EMBEDDING_DIMENSIONS` does not match the column, Postgres rejects the insert,
and the rejection lands inside the `except Exception` of `src/services/ingestion.py`, which
logs it as "embedding unavailable", stores `full_text` and marks the document **READY**.
What is left is an apparently correct document that cannot be retrieved by RAG.

Everything here is a unit test: `EmbeddingCheck` is a dataclass over two integers, so the
cases are built by hand with no database.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.services.embedding_check import EmbeddingCheck


class TestStatus:
    def test_matching_dimensions_are_ok(self):
        assert EmbeddingCheck(configured=768, column=768).status == "ok"

    def test_differing_dimensions_are_a_mismatch(self):
        assert EmbeddingCheck(configured=384, column=768).status == "mismatch"

    def test_an_unconstrained_column_is_told_apart_from_a_mismatch(self):
        """`vector` with no dimension works, but stops validating: neither ok nor error."""
        assert EmbeddingCheck(configured=768, column=None).status == "unconstrained"


class TestDetail:
    def test_a_match_has_nothing_to_say(self):
        assert EmbeddingCheck(configured=768, column=768).detail is None

    def test_a_mismatch_names_both_numbers(self):
        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "384" in detail
        assert "vector(768)" in detail

    def test_a_mismatch_warns_that_the_failure_is_invisible(self):
        """What makes the message useful: without this nobody knows where to look."""
        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "no visible error" in detail

    def test_with_a_truncatable_model_the_fix_is_one_line_of_the_env(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """`text-embedding-3-*` accepts `dimensions`, so there is nothing to migrate."""
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")

        detail = EmbeddingCheck(configured=1536, column=768).detail

        assert detail is not None
        assert "EMBEDDING_DIMENSIONS=768" in detail
        assert "migrate" not in detail

    def test_with_a_fixed_dimension_model_the_fix_is_to_migrate(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Do not promise an easy fix when the model cannot truncate."""
        monkeypatch.setattr(settings, "EMBEDDING_MODEL", "multilingual-e5-small")

        detail = EmbeddingCheck(configured=384, column=768).detail

        assert detail is not None
        assert "migrate the column" in detail
        assert "re-ingest" in detail

    def test_an_unconstrained_column_explains_what_was_expected(self):
        detail = EmbeddingCheck(configured=768, column=None).detail

        assert detail is not None
        assert "vector(768)" in detail
        assert "0008" in detail


class TestDimensionsParameter:
    """`(c)`: asking the provider for the dimension is what makes "one key and done" true."""

    def _service(self, model: str):
        from src.llm.embedding import EmbeddingConfig, EmbeddingService

        return EmbeddingService(
            EmbeddingConfig(model=model, api_base=None, api_key="k", dimensions=768)
        )

    def test_it_is_sent_to_text_embedding_3(self):
        """1536 out of the box; without asking for 768 it does not fit the column."""
        kwargs = self._service("text-embedding-3-small")._kwargs(["hola"])

        assert kwargs["dimensions"] == 768

    def test_it_goes_to_the_large_variant_too(self):
        kwargs = self._service("text-embedding-3-large")._kwargs(["hola"])

        assert kwargs["dimensions"] == 768

    def test_it_is_not_sent_to_a_provider_that_does_not_know_it(self):
        """Sending it where it is unsupported is an error, not an ignored hint."""
        for model in ("ollama/paraphrase-multilingual", "multilingual-e5-base"):
            assert "dimensions" not in self._service(model)._kwargs(["hola"])
