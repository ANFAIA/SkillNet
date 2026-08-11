"""NotebookLM-style image **prompt builders** shared by the visual generators.

The approved gallery look (``scripts/render_notebooklm_visuals.py``) is a flat, modern
editorial vector illustration in a muted professional palette. These are the pure functions
that compose the per-artifact prompt from an already-grounded spec, so every generator
speaks the same visual language; the image call itself lives in
:func:`src.services.media.images.generate_image`.

Full-image generation is intended (the gallery look was approved): the whole sheet/slide is
the generated image, minor text imperfections accepted — never a text-overlay hybrid. The
factual grounding still lives in ``spec_json`` (the citations panel reads it); the image is
the visual surface built from that same spec.
"""

from __future__ import annotations

#: The house style shared with the approved gallery visuals (kept in sync with
#: ``scripts/render_notebooklm_visuals.py``).
STYLE = (
    "Flat, modern editorial vector illustration, NotebookLM style. Muted professional palette "
    "(warm sand, deep teal, soft charcoal), clean line icons, generous whitespace, subtle grain, "
    "high quality, crisp legible Spanish text, no watermark, no logos."
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
    body = _clip(" | ".join(pieces))
    subtitle = f" Subtitulo: '{info.subtitle}'." if info.subtitle else ""
    return (
        f"A tall PORTRAIT editorial INFOGRAPHIC poster in Spanish titled '{info.title}'."
        f"{subtitle} Stacked sections, each with a big bold number or stat and a clean line "
        "icon, clear visual hierarchy and generous whitespace, vertical layout, "
        f"training/onboarding aesthetic. Secciones: {body}. " + STYLE
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
        elif kind == "table":
            parts.append(" · ".join(block.headers))
        elif kind == "chart":
            parts.append(block.title)
    return _clip(" ".join(parts))


def slide_prompt(slide) -> str:
    """A 16:9 LANDSCAPE slide-illustration prompt built from a validated ``Slide``.

    Composes the slide title, optional subtitle, and a flattened summary of its blocks into
    one illustration brief. Pure — takes the spec, returns a string.
    """
    subtitle = f" Subtitulo: '{slide.subtitle}'." if slide.subtitle else ""
    body = slide_body_text(slide)
    content = f" Contenido a ilustrar: {body}." if body else ""
    return (
        f"A 16:9 LANDSCAPE slide ILLUSTRATION in Spanish for a training presentation, "
        f"escena titulada '{slide.title}'.{subtitle}{content} One clear illustrative scene "
        "with clean line icons, no dense paragraphs, only a short Spanish caption. " + STYLE
    )


__all__ = ["STYLE", "infographic_prompt", "slide_body_text", "slide_prompt"]
