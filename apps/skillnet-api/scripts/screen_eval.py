"""Offline eval for assembled learning screens.

Usage::

    uv run python scripts/screen_eval.py scenarios.json

The input is a JSON object with ``cases`` and optional ``ignore_types``.  Each case has
``id``, ``objective``, ``ui_spec`` and optionally ``blueprint``, ``central_intents`` and
``critical_facts``.  A critical fact is ``{"id": "emergency", "any_of": ["112"]}``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.runtime.screen_eval import (  # noqa: E402
    CriticalFact,
    ScreenScenario,
    evaluate_corpus,
    evaluate_screen,
)


def _scenario(raw: dict[str, Any]) -> ScreenScenario:
    facts = tuple(
        CriticalFact(id=str(fact["id"]), any_of=tuple(map(str, fact["any_of"])))
        for fact in raw.get("critical_facts", [])
    )
    return ScreenScenario(
        id=str(raw["id"]),
        objective=str(raw["objective"]),
        ui_spec=raw["ui_spec"],
        blueprint=raw.get("blueprint"),
        central_intents=tuple(map(str, raw.get("central_intents", ["concepto"]))),
        critical_facts=facts,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalua pantallas sin red ni LLM")
    parser.add_argument("input", type=Path, help="manifest JSON con casos reproducibles")
    parser.add_argument("--out", type=Path, help="escribe tambien el informe JSON")
    parser.add_argument("--redundancy-threshold", type=float, default=0.72)
    args = parser.parse_args()

    manifest = json.loads(args.input.read_text(encoding="utf-8"))
    screens = [
        evaluate_screen(_scenario(raw), redundancy_threshold=args.redundancy_threshold)
        for raw in manifest.get("cases", [])
    ]
    corpus = evaluate_corpus(screens, ignore_types=manifest.get("ignore_types", []))
    report = {"screens": [screen.as_dict() for screen in screens], "corpus": corpus.as_dict()}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
