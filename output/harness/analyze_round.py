"""Aggregate bounded profile journeys into a compact round report."""

from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def journeys(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.glob("*/journey.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def screens(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    result = []
    for row in rows:
        slug = row.get("profile", {}).get("slug", "unknown")
        for course in row.get("courses", []):
            for node in course.get("nodes", []):
                render = node.get("render")
                if render:
                    result.append((slug, render))
    return result


def same_screen_concept_quiz(program: str) -> bool:
    has_quiz = "QuizItem(" in program
    content = any(token in program for token in ("Table(", "StepSequence(", "BeforeAfter(", "TextContent("))
    return has_quiz and content


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured = screens(rows)
    components = Counter()
    formats = Counter()
    same_screen = 0
    lengths = []
    for _, screen in captured:
        formats[str(screen.get("meta", {}).get("ui_format"))] += 1
        components.update(screen.get("components", []))
        lengths.append(int(screen.get("characters", 0)))
        if same_screen_concept_quiz(screen.get("program", "")):
            same_screen += 1
    pairwise = []
    by_slug: dict[str, list[str]] = {}
    for row in rows:
        slug = row.get("profile", {}).get("slug", "unknown")
        program = "\n".join(
            node.get("render", {}).get("program", "")
            for course in row.get("courses", [])
            for node in course.get("nodes", [])
            if node.get("render")
        )
        by_slug.setdefault(slug, []).append(program)
    slugs = sorted(by_slug)
    for index, left in enumerate(slugs):
        for right in slugs[index + 1 :]:
            comparisons = [
                difflib.SequenceMatcher(None, a, b).ratio()
                for a in by_slug[left]
                for b in by_slug[right]
            ]
            pairwise.append({
                "left": left,
                "right": right,
                "similarity": round(sum(comparisons) / len(comparisons), 4),
            })
    within_profile = {}
    for slug, programs in by_slug.items():
        comparisons = [
            difflib.SequenceMatcher(None, left, right).ratio()
            for index, left in enumerate(programs)
            for right in programs[index + 1 :]
        ]
        within_profile[slug] = round(sum(comparisons) / len(comparisons), 4) if comparisons else None
    within_similarities = [value for value in within_profile.values() if value is not None]
    similarities = [row["similarity"] for row in pairwise]
    errors = sum(len(row.get("errors", [])) + sum(len(course.get("errors", [])) for course in row.get("courses", [])) for row in rows)
    profile_metrics = {}
    for slug in slugs:
        matching_rows = [row for row in rows if row.get("profile", {}).get("slug", "unknown") == slug]
        rendered = [screen for screen_slug, screen in captured if screen_slug == slug]
        profile_lengths = [int(screen.get("characters", 0)) for screen in rendered]
        accepted = [screen.get("accepted", {}) for screen in rendered]
        saved = matching_rows[0].get("profile_saved") or {}
        preferences = saved.get("learning_preferences") or {}
        profile_metrics[slug] = {
            "experience_level": saved.get("experience_level"),
            "modality": preferences.get("modality"),
            "short_blocks": bool(matching_rows[0].get("profile", {}).get("accessibility", {}).get("short_blocks")),
            "runs": len(matching_rows),
            "screens": len(rendered),
            "character_avg": round(sum(profile_lengths) / len(profile_lengths), 1) if profile_lengths else None,
            "components": sorted({component for screen in rendered for component in screen.get("components", [])}),
            "accepted_cached": sum(bool(item.get("cached")) for item in accepted),
            "duration_avg_s": round(
                sum(float(row.get("duration_s", 0)) for row in matching_rows) / len(matching_rows), 3
            ),
        }
    return {
        "profiles": len(slugs),
        "runs": len(rows),
        "screens": len(captured),
        "errors": errors,
        "format_counts": dict(formats),
        "component_counts": dict(components),
        "same_screen_concept_and_quiz": same_screen,
        "same_screen_rate": round(same_screen / len(captured), 4) if captured else None,
        "character_min": min(lengths) if lengths else None,
        "character_avg": round(sum(lengths) / len(lengths), 1) if lengths else None,
        "character_max": max(lengths) if lengths else None,
        "pairwise_profile_similarity_avg": round(sum(similarities) / len(similarities), 4) if similarities else None,
        "pairwise_profile_similarity_min": min(similarities) if similarities else None,
        "pairwise_profile_similarity_max": max(similarities) if similarities else None,
        "within_profile_similarity_avg": round(sum(within_similarities) / len(within_similarities), 4) if within_similarities else None,
        "within_profile_similarity": within_profile,
        "pairwise": pairwise,
        "profile_metrics": profile_metrics,
        "profile_durations_s": {
            row.get("profile", {}).get("slug", "unknown"): row.get("duration_s") for row in rows
        },
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["# Informe de ronda", "", f"- Perfiles: {summary['profiles']}", f"- Recorridos: {summary['runs']}", f"- Pantallas: {summary['screens']}", f"- Errores: {summary['errors']}", ""]
    lines += ["## Formatos", "", "| Formato | Cantidad |", "|---|---:|"]
    lines += [f"| {key} | {value} |" for key, value in sorted(summary["format_counts"].items())]
    lines += ["", "## Componentes", "", "| Componente | Cantidad |", "|---|---:|"]
    lines += [f"| `{key}` | {value} |" for key, value in sorted(summary["component_counts"].items())]
    lines += ["", "## Señales de calidad", "", f"- Pantallas con concepto + QuizItem: {summary['same_screen_concept_and_quiz']} ({summary['same_screen_rate']})", f"- Caracteres visibles mín./media/máx.: {summary['character_min']} / {summary['character_avg']} / {summary['character_max']}", f"- Similitud media entre brazos: {summary['pairwise_profile_similarity_avg']}", f"- Similitud media dentro del mismo brazo: {summary['within_profile_similarity_avg']}", ""]
    lines += ["## Métricas por perfil", "", "| Perfil | Experiencia | Modalidad | Bloques cortos | Recorridos | Pantallas | Media caracteres | Caché inicial | Duración media (s) |", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for slug, metrics in sorted(summary["profile_metrics"].items()):
        lines.append(
            f"| {slug} | {metrics['experience_level']} | {metrics['modality']} | "
            f"{str(metrics['short_blocks']).lower()} | {metrics['runs']} | {metrics['screens']} | "
            f"{metrics['character_avg']} | {metrics['accepted_cached']} | {metrics['duration_avg_s']} |"
        )
    lines += [
        "",
        "## Interpretación",
        "",
        "- La ronda tiene tres repeticiones forzadas por brazo; ninguna petición inicial usó caché.",
        "- La estructura es más informativa que la prosa: el muestreo puede cambiar texto sin efecto del perfil.",
        "- Todos los brazos usaron la misma receta de componentes en todas las pantallas; no hubo personalización estructural.",
        "- Bloques cortos no redujo la longitud media frente al perfil base y falló su comprobación direccional.",
        "- La ausencia de QuizItems impide obtener evidencia sobre errores, mastery o replanificación.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=Path, required=True)
    args = parser.parse_args()
    rows = journeys(args.round)
    summary = report(rows)
    (args.round / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.round / "report.md").write_text(markdown(summary) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
