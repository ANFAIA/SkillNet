#!/usr/bin/env python
"""Tune knowledge-pack extraction without rendering or mutating courses.

The default matrix is 3 policies x 3 benchmark nodes x 2 model passes.  Policies can
be selected for a gated follow-up instead of paying to repeat settled variables.  A
provider-call cap makes the promised upper bound executable, not just documentary.
Every completed cell is checkpointed so rejected packs remain useful evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

import litellm  # noqa: E402

from quality_bench import (  # noqa: E402
    CORPUS_BY_NAME,
    COURSE_ID,
    ORG_ID,
    SCHEMA_VERSION,
    PackBenchPolicy,
    assess_completed_pack,
    build_session,
)
from src.agents.runtime.router import tier_llm  # noqa: E402
from src.config import settings  # noqa: E402
from src.knowledge_pack.configured_generator import (  # noqa: E402
    ConfiguredKnowledgePackGenerator,
)
from src.services.node_knowledge_pack_service import KnowledgePackSnapshot  # noqa: E402

NODE_NAMES = (
    "apertura-cierre-caja",
    "alergenos-hosteleria",
    "atencion-reclamaciones",
)


@dataclass(frozen=True)
class Variant:
    name: str
    policy: PackBenchPolicy


VARIANTS = (
    Variant(
        "compact",
        PackBenchPolicy(
            extractor_max_tokens=1_200,
            reviewer_max_tokens=1_200,
            min_invariants=1,
            min_fact_coverage=0.80,
            require_evidence=False,
        ),
    ),
    Variant(
        "balanced",
        PackBenchPolicy(
            extractor_max_tokens=1_600,
            reviewer_max_tokens=1_600,
            min_invariants=3,
            min_fact_coverage=1.0,
            require_evidence=True,
        ),
    ),
    Variant(
        "coverage",
        PackBenchPolicy(
            extractor_max_tokens=2_048,
            reviewer_max_tokens=2_048,
            min_invariants=5,
            min_fact_coverage=1.0,
            require_evidence=True,
        ),
    ),
    Variant(
        "traceable",
        PackBenchPolicy(
            extractor_max_tokens=3_200,
            reviewer_max_tokens=3_200,
            min_invariants=5,
            max_atoms=32,
            min_fact_coverage=1.0,
            require_evidence=True,
        ),
    ),
)


class ProviderCallCap:
    def __init__(self, maximum: int, *, initial: int = 0) -> None:
        self.maximum = maximum
        self.calls = initial
        self.input_tokens = 0
        self.output_tokens = 0
        self._original = litellm.acompletion

    async def __call__(self, **kwargs: Any) -> Any:
        if self.calls >= self.maximum:
            raise RuntimeError(f"provider call cap reached ({self.maximum})")
        self.calls += 1
        response = await self._original(**kwargs)
        usage = getattr(response, "usage", None)
        self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        return response


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cost(tokens_in: int | None, tokens_out: int | None, args: argparse.Namespace) -> float:
    return round(
        ((tokens_in or 0) * args.price_in + (tokens_out or 0) * args.price_out)
        / 1_000_000,
        8,
    )


def _write(out: Path, payload: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = payload["results"]
    lines = [
        "# Ajuste de Node Knowledge Packs",
        "",
        f"- Modelo: `{payload['model']}`",
        f"- Llamadas reales al proveedor: {payload['provider_calls']} / {payload['call_cap']}",
        "- Alcance: extracción + revisión; sin renders y sin escritura en cursos.",
        "",
        "| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["outcome"] == "error":
            lines.append(
                f"| {row['variant']} | {row['node']} | ERROR | — | — | — | "
                f"{row.get('input_tokens', 0)}/{row.get('output_tokens', 0)} | "
                f"{row.get('duration_ms', 0)} ms | ${row.get('cost_usd', 0):.6f} |"
            )
            continue
        result = "PASS" if row["passed"] else "FAIL"
        lines.append(
            f"| {row['variant']} | {row['node']} | {result} | "
            f"{row['fact_coverage']:.0%} | {row['invariant_count']} | "
            f"{row['required_evidence_count']} | {row['input_tokens']}/{row['output_tokens']} | "
            f"{row['duration_ms']} ms | ${row['cost_usd']:.6f} |"
        )
    lines.extend(["", "## Fallos de política", ""])
    failures = [row for row in rows if row.get("failures") or row["outcome"] == "error"]
    if failures:
        for row in failures:
            reasons = row.get("failures") or [row.get("error", "error desconocido")]
            lines.append(f"- **{row['variant']} / {row['node']}**: {'; '.join(reasons)}")
    else:
        lines.append("Ninguno.")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    if not settings.LLM_API_KEY:
        print("Falta LLM_API_KEY; no se ha hecho ninguna llamada.", file=sys.stderr)
        return 2
    settings.LLM_MODEL = args.model
    settings.LLM_RUNTIME_FAST_MODEL = args.model
    settings.LLM_RUNTIME_HEAVY_MODEL = args.model
    settings.LLM_MAX_ATTEMPTS = 1

    checkpoint = args.out / "results.json"
    previous: dict[str, Any] | None = None
    if checkpoint.exists():
        previous = json.loads(checkpoint.read_text(encoding="utf-8"))
        if previous.get("model") != args.model or previous.get("call_cap") != args.call_cap:
            print("El checkpoint pertenece a otra configuración.", file=sys.stderr)
            return 2
    cap = ProviderCallCap(
        args.call_cap, initial=int(previous.get("provider_calls", 0)) if previous else 0
    )
    litellm.acompletion = cap  # type: ignore[assignment]
    llm = tier_llm({}, "heavy")
    selected_variants = tuple(item for item in VARIANTS if item.name in args.variants)
    selected_nodes = tuple(item for item in NODE_NAMES if item in args.nodes)
    payload: dict[str, Any] = previous or {
        "schema": "skillnet-pack-tuning/2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "call_cap": args.call_cap,
        "provider_calls": 0,
        "prices_per_million": {"input": args.price_in, "output": args.price_out},
        "variants": [
            {"name": item.name, "policy": asdict(item.policy)}
            for item in selected_variants
        ],
        "nodes": list(selected_nodes),
        "results": [],
    }
    completed_cells = {
        (row["variant"], row["node"]) for row in payload["results"]
    }
    for variant in selected_variants:
        generator = ConfiguredKnowledgePackGenerator(
            llm,
            extractor_max_tokens=variant.policy.extractor_max_tokens,
            reviewer_max_tokens=variant.policy.reviewer_max_tokens,
        )
        for node_name in selected_nodes:
            if (variant.name, node_name) in completed_cells:
                continue
            encargo = CORPUS_BY_NAME[node_name]
            print(f"[{cap.calls:02d}/{args.call_cap}] {variant.name} / {node_name}", flush=True)
            session = build_session(encargo)
            cell_started = time.perf_counter()
            input_before = cap.input_tokens
            output_before = cap.output_tokens
            try:
                completed = await generator.generate(
                    course=session.course,
                    node=session.node,
                    source_context=encargo.source_text,
                    snapshot=KnowledgePackSnapshot(
                        org_id=ORG_ID,
                        course_id=COURSE_ID,
                        node_id=session.node.id,
                        source_fingerprint=_digest(encargo.source_text),
                        schema_version=SCHEMA_VERSION,
                        generator_version=f"knowledge-pack/v2-tuning-{variant.name}",
                    ),
                )
                assessment = assess_completed_pack(completed, encargo, variant.policy)
                payload["results"].append(
                    {
                        "variant": variant.name,
                        "node": node_name,
                        "outcome": "completed",
                        "passed": assessment.passed,
                        **asdict(assessment),
                        "pack_hash": completed.pack_hash,
                        "pack_payload": completed.pack_payload,
                        "markdown": completed.markdown,
                        "input_tokens": completed.input_tokens,
                        "output_tokens": completed.output_tokens,
                        "duration_ms": completed.duration_ms,
                        "cost_usd": _cost(
                            completed.input_tokens, completed.output_tokens, args
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - failed cells are benchmark data.
                cell_input = cap.input_tokens - input_before
                cell_output = cap.output_tokens - output_before
                payload["results"].append(
                    {
                        "variant": variant.name,
                        "node": node_name,
                        "outcome": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                        "input_tokens": cell_input,
                        "output_tokens": cell_output,
                        "duration_ms": round((time.perf_counter() - cell_started) * 1000),
                        "cost_usd": _cost(cell_input, cell_output, args),
                    }
                )
            payload["provider_calls"] = cap.calls
            _write(args.out, payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--call-cap", type=int, default=18)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=[item.name for item in VARIANTS],
        default=[item.name for item in VARIANTS],
    )
    parser.add_argument(
        "--nodes",
        nargs="+",
        choices=list(NODE_NAMES),
        default=list(NODE_NAMES),
    )
    parser.add_argument("--price-in", type=float, default=0.15)
    parser.add_argument("--price-out", type=float, default=0.60)
    args = parser.parse_args()
    expected_calls = len(set(args.variants)) * len(set(args.nodes)) * 2
    if args.call_cap != expected_calls:
        parser.error(
            f"selected matrix requires --call-cap {expected_calls} "
            "(variants x nodes x extractor/reviewer)"
        )
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
