"""Unit tests for the local raw-vs-pack quality-bench arm.

The experiment must remain a bench-only seam: these tests deliberately import the script
instead of any production runtime extension.
"""

from types import SimpleNamespace

import pytest

from src.llm.client import Usage
from scripts import quality_bench as bench


SOURCE = """# Servicio seguro

1. Confirma la mesa antes de registrar la comanda.

Nunca envíes un plato con un alérgeno sin marcar.

Explica el retraso antes de que el cliente tenga que preguntarlo.
"""


def _run(arm: str) -> bench.RunResult:
    return bench.RunResult(
        encargo="comanda",
        repeat=1,
        arm=arm,
        context="raw_source" if arm == "raw" else "knowledge_pack",
        outcome="first_pass",
        ui_format="explanation",
        tier="fast",
        model="fixture/bench",
        decide_called=False,
        attempts=1,
        seconds=1.0 if arm == "raw" else 2.0,
        tokens_in=10,
        tokens_out=3,
        cost_usd=0.0,
        tokens_measured=True,
        render_status="ready",
        steps=["load_context"],
        cache_key="key",
    )


def test_knowledge_pack_is_deterministic_and_keeps_all_source_atoms() -> None:
    pack = bench.KnowledgePack.from_source(SOURCE)

    first = pack.select(profile={"preset": "visual"})
    second = pack.select(profile={"preset": "visual"})

    assert first == second
    assert first.atom_ids == first.invariant_ids
    assert len(first.atom_ids) == 4
    assert pack.source_digest == bench._digest(SOURCE)
    assert "# Dossier de referencia del nodo" in first.markdown
    assert all(atom.text in first.markdown for atom in pack.atoms)


def test_pack_replaces_only_source_context_and_traces_same_source() -> None:
    result = {
        "source_context": SOURCE,
        "node": {"id": "node-1"},
        "profile": {"preset": "practical"},
        "cache_key": "unchanged",
    }
    raw_recorder = bench.Recorder(encargo="comanda", request_id="raw", arm="raw")
    pack_recorder = bench.Recorder(encargo="comanda", request_id="pack", arm="pack")

    raw = bench._replace_bench_context(result, raw_recorder)
    packed = bench._replace_bench_context(result, pack_recorder)

    assert raw is result
    assert raw["source_context"] == SOURCE
    assert packed["source_context"] != SOURCE
    assert packed["node"] == result["node"]
    assert packed["profile"] == result["profile"]
    assert packed["cache_key"] == result["cache_key"]
    assert raw_recorder.source_digest == pack_recorder.source_digest
    assert raw_recorder.atom_ids == pack_recorder.atom_ids
    assert pack_recorder.context_kind == "knowledge_pack"
    assert pack_recorder.context_digest != pack_recorder.source_digest


def test_aggregation_never_mixes_raw_and_pack() -> None:
    grouped = bench.aggregate_by_arm([_run("raw"), _run("pack")])

    assert set(grouped) == {"raw", "pack"}
    assert grouped["raw"][1].runs == 1
    assert grouped["pack"][1].runs == 1
    assert grouped["raw"][1].summary()["p50_seconds"] == 1.0
    assert grouped["pack"][1].summary()["p50_seconds"] == 2.0


def test_ui_signature_hashes_only_a_served_canonical_spec() -> None:
    render = SimpleNamespace(ui_spec={"components": [{"id": "a", "type": "Callout"}]})

    assert bench._ui_signature(render) == bench._ui_signature(render)
    assert bench._ui_signature(SimpleNamespace(ui_spec=None)) == ""


def test_parser_defaults_to_raw_and_exposes_both_arms() -> None:
    parser = bench.build_parser()

    assert parser.parse_args([]).arm == "raw"
    assert parser.parse_args(["--arm", "both"]).arm == "both"
    assert parser.parse_args([]).pack_source == "structural"
    assert parser.parse_args(["--pack-source", "generated"]).pack_source == "generated"
    tuned = parser.parse_args(
        [
            "--pack-extractor-tokens", "1200",
            "--pack-reviewer-tokens", "1800",
            "--pack-min-invariants", "3",
            "--pack-max-atoms", "16",
            "--pack-min-fact-coverage", "0.85",
            "--pack-require-evidence",
        ]
    )
    assert tuned.pack_extractor_tokens == 1200
    assert tuned.pack_reviewer_tokens == 1800
    assert tuned.pack_min_invariants == 3
    assert tuned.pack_max_atoms == 16
    assert tuned.pack_min_fact_coverage == 0.85
    assert tuned.pack_require_evidence is True


class GroundedPackLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.ref_id = ""
        self.unit_ids: list[str] = []

    async def complete_with_usage(self, _system, user, **_kwargs):
        import json

        self.calls += 1
        if user.lstrip().startswith("{"):
            prompt = json.loads(user)
            self.ref_id = prompt["sources"][0]["ref"]["ref_id"]
            self.unit_ids = [
                item["unit_id"]
                for item in prompt["sources"][0]["coverage_units"]
            ]
        ref_id = self.ref_id
        payload = {
            "evidence_specs": [
                {
                    "evidence_id": "evidence.rule",
                    "description": "Aplica la regla operativa.",
                    "atom_refs": ["fact.rule"],
                    "required": True,
                }
            ],
            "must_preserve": [
                {
                    "atom_id": "fact.rule",
                    "kind": "fact",
                    "text": "Conserva la regla operativa de la fuente.",
                    "sources": [ref_id],
                    "source_units": self.unit_ids,
                    "evidence": ["evidence.rule"],
                    "critical": True,
                }
            ],
            "selectable": [],
            "generable_slots": [],
            "missing_data": [],
        }
        return json.dumps(payload), Usage(tokens_in=12, tokens_out=4)


async def test_generated_pack_source_runs_the_real_two_pass_contract() -> None:
    llm = GroundedPackLLM()
    encargo = bench.CORPUS_BY_NAME["extintor"]

    artifacts = await bench.prepare_generated_packs([encargo], llm=llm)

    artifact = artifacts[encargo.name]
    assert llm.calls == 2
    assert artifact.input_tokens == 24
    assert artifact.output_tokens == 8
    assert artifact.selection.invariant_ids == ("must.fact.rule",)
    assert len(artifact.pack_hash) == 64


async def test_bench_session_returns_no_persisted_pack_to_both_arms() -> None:
    from src.repositories.node_knowledge_pack_repo import NodeKnowledgePackRepository

    session = bench.build_session(bench.CORPUS_BY_NAME["extintor"])

    record = await NodeKnowledgePackRepository(session).find_ready_for_schema(
        node_id=session.node.id,
        schema_version=1,
        generator_version="knowledge-pack-generator/1",
    )

    assert record is None


def test_fact_coverage_is_accent_insensitive_and_requires_every_term() -> None:
    checks = (
        bench.PackFactCheck("written", ("por escrito", "antes")),
        bench.PackFactCheck("folder", ("carpeta roja",)),
    )
    payload = {
        "must_preserve": [
            {"text": "Información POR ESCRITO disponible antes de pedir."}
        ],
        "selectable": [],
        "evidence_specs": [],
        "generable_slots": [],
        "missing_data": [],
    }

    coverage, matched, missing = bench.evaluate_pack_facts(payload, checks)

    assert coverage == 0.5
    assert matched == ("written",)
    assert missing == ("folder",)


async def test_quality_policy_rejects_a_valid_but_too_thin_pack() -> None:
    llm = GroundedPackLLM()
    encargo = bench.CORPUS_BY_NAME["extintor"]

    with pytest.raises(ValueError, match="invariants 1 < minimum 2"):
        await bench.prepare_generated_packs(
            [encargo],
            llm=llm,
            policy=bench.PackBenchPolicy(min_invariants=2),
        )
