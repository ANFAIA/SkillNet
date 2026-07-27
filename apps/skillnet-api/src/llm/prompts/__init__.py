"""System prompts and user-prompt builders for the generation pipeline."""

from src.llm.prompts.generation import (
    CONTENT_REFINER_SYSTEM,
    MODULE_GENERATOR_SYSTEM,
    QUALITY_REVIEWER_SYSTEM,
    STRUCTURE_DESIGNER_SYSTEM,
    THEME_EXTRACTOR_SYSTEM,
    build_extraction_prompt,
    build_module_prompt,
    build_refine_prompt,
    build_review_prompt,
    build_structure_prompt,
)
from src.llm.prompts.source import SOURCE_WRITER_SYSTEM, build_source_prompt

__all__ = [
    "SOURCE_WRITER_SYSTEM",
    "build_source_prompt",
    "THEME_EXTRACTOR_SYSTEM",
    "STRUCTURE_DESIGNER_SYSTEM",
    "MODULE_GENERATOR_SYSTEM",
    "QUALITY_REVIEWER_SYSTEM",
    "CONTENT_REFINER_SYSTEM",
    "build_extraction_prompt",
    "build_structure_prompt",
    "build_module_prompt",
    "build_review_prompt",
    "build_refine_prompt",
]
