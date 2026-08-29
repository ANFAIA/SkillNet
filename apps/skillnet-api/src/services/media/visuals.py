"""Image **prompt builders** shared by the visual generators.

These pure functions compose a restrained enterprise visual brief from an already-grounded
spec; the image call itself lives in
:func:`src.services.media.images.generate_image`.

Full-image generation is intended (the gallery look was approved): the whole sheet/slide is
the generated image, minor text imperfections accepted — never a text-overlay hybrid. The
factual grounding still lives in ``spec_json`` (the citations panel reads it); the image is
the visual surface built from that same spec.
"""

from __future__ import annotations

#: A clean, generic enterprise poster language. Infographics remain a single generated image,
#: but no longer imitate NotebookLM or introduce decorative brand-like colour and texture.
INFOGRAPHIC_STYLE = (
    "Clean professional enterprise infographic on a pure white background. Black and charcoal "
    "typography, thin neutral-gray rules, restrained black line icons, precise alignment, "
    "generous whitespace and a clear editorial grid. Flat print-design finish. No colour accents, "
    "no gradients, no grain, no shadows, no floating rounded cards, no decorative blobs, no "
    "watermark and no logos."
)

#: Slide art is an ingredient inside a layout rendered by SkillNet, not a generated slide.
#: Keeping this separate lets posters and deck illustrations use different compositions while
#: retaining the same clean monochrome direction.
SLIDE_ILLUSTRATION_STYLE = (
    "Minimal black line illustration on a pure white background. Clean editorial vector "
    "drawing, restrained geometric forms, consistent thin strokes, generous empty space, "
    "professional enterprise tone. No colour, no gradients, no texture, no shadow, no "
    "watermark, no logo, no border. Absolutely no text, letters, words, numbers, labels, "
    "captions, charts or user-interface elements."
)

#: Keep prompts bounded — a wall of source text hurts the image, not helps it.
_MAX_BODY_CHARS = 420


def _clip(text: str, limit: int = _MAX_BODY_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def infographic_prompt(info) -> str:
    """A tall PORTRAIT infographic-poster prompt built from a validated ``Infographic``.

    Composes the title, optional subtitle, and each section's ``stat``/``heading``/
    ``one_line`` into one editorial-poster brief. Pure — takes the spec, returns a string.
    """
    pieces: list[str] = []
    for section in info.sections:
        head = f"{section.stat} — {section.heading}" if section.stat else section.heading
        pieces.append(f"{head}: {section.one_line}")
    body = _clip(" | ".join(pieces), 700)
    subtitle = f" Subtitulo: '{info.subtitle}'." if info.subtitle else ""
    layout = getattr(info, "layout", "auto")
    layout_instruction = {
        "flow": "Arrange the sections as one clear vertical sequence connected by thin arrows.",
        "comparison": "Arrange the sections in two balanced comparison columns.",
        "grid": "Arrange the sections in a strict, evenly aligned editorial grid.",
        "hierarchy": "Arrange one leading idea at the top with subordinate branches below.",
        "auto": "Choose the simplest editorial arrangement that matches the supplied ideas.",
    }.get(layout, "Choose the simplest editorial arrangement that matches the supplied ideas.")
    return (
        f"Create one tall PORTRAIT editorial INFOGRAPHIC poster in Spanish. Exact title: "
        f"'{info.title}'.{subtitle} Use a disciplined top-to-bottom reading order and 3-6 "
        f"clearly separated sections. {layout_instruction} Give genuine statistics strong "
        "typographic emphasis; give "
        "non-numeric sections a small line icon instead. Render ONLY this exact supplied copy, "
        "with no invented headings, captions or footer text. Supplied sections: "
        f"{body}. {INFOGRAPHIC_STYLE} Keep every word large, crisp and legible."
    )


def slide_body_text(slide) -> str:
    """Flatten a ``Slide``'s kit blocks into a short text summary for the image prompt.

    Pure. Understands the block vocabulary (text/callout/steps/table/chart) and pulls the
    human-readable gist out of each, clipped so the prompt stays bounded.
    """
    parts: list[str] = []
    for block in slide.blocks:
        kind = getattr(block, "type", None)
        if kind in ("text", "callout"):
            parts.append(block.text)
        elif kind == "steps":
            parts.append(f"{block.title}: " + "; ".join(block.steps))
        elif kind == "timeline":
            parts.append(f"{block.label}: " + "; ".join(block.steps))
        elif kind == "card":
            parts.append(f"{block.title}: {block.text}")
        elif kind == "table":
            parts.append(" · ".join(block.headers))
        elif kind == "chart":
            parts.append(block.title)
    return _clip(" ".join(parts))


def slide_prompt(slide) -> str:
    """A supporting illustration prompt built from a validated ``Slide``.

    The old prompt asked the image model for a complete slide and repeated its title/body,
    which invited it to draw misspelled copy. The shared web canvas now owns all typography;
    this prompt asks only for one text-free visual ingredient.
    """
    brief = (getattr(slide, "visual_brief", None) or "").strip()
    if not brief:
        # Video decks no longer ask the content model for an image brief. Feeding the whole
        # body to the image model made it reproduce labels and paragraphs; the title carries
        # enough semantic direction for one supporting metaphor.
        brief = slide.title
    return (
        "Create one isolated supporting illustration for an educational video. Depict one "
        "simple visual metaphor or scene, not a diagram, infographic, flowchart, chart, "
        "presentation slide or user interface. "
        f"Concept to depict visually: {_clip(brief)}. " + SLIDE_ILLUSTRATION_STYLE
    )


__all__ = [
    "INFOGRAPHIC_STYLE",
    "SLIDE_ILLUSTRATION_STYLE",
    "infographic_prompt",
    "slide_body_text",
    "slide_prompt",
]
