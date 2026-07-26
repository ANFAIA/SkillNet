"""The SkillNet UI Kit — the frozen catalogue of §5.3.

This module is the **single source of truth** for the component list, the exact
prop names and the *positional* order the OpenUI dialect uses. Validation
(``src/render/spec.py``) and the prompt fragment
(``src/render/backends/openui.py::prompt_fragment``) are both generated from here,
so the prompt can never drift from the validator — §5.4: "generado desde el kit,
nunca escrito a mano dos veces".

Two closed lists are imported instead of retyped, so they cannot drift either:
``ExerciseType`` (the six ``item_type`` values, §5.3) and ``BLOOM_LEVELS`` (the six
values the ``node_attempts.bloom_level`` CHECK accepts, §3.4).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from src.models.exercise import ExerciseType
from src.models.node_attempt import BLOOM_LEVELS

GAP_VALUES: tuple[str, ...] = ("sm", "md", "lg")
TEXT_VARIANTS: tuple[str, ...] = ("body", "lead", "caption")
CALLOUT_TONES: tuple[str, ...] = ("info", "warn", "success")
CHART_KINDS: tuple[str, ...] = ("bar", "line")
ITEM_TYPES: tuple[str, ...] = tuple(m.value for m in ExerciseType)

#: The ``variant`` a ``TextContent`` must carry to satisfy contract rule 7 (§5.2).
LEAD_VARIANT = "lead"


class PropKind(str, enum.Enum):
    """The value shapes the dialect can express."""

    STRING = "string"
    ENUM = "enum"
    STRING_LIST = "string[]"
    STRING_MATRIX = "string[][]"
    NUMBER_LIST = "number[]"
    #: Array of component ids. Maps to ``Component.children``, never to ``props``.
    REFS = "ref[]"


@dataclass(frozen=True, slots=True)
class PropSpec:
    name: str
    kind: PropKind
    description: str
    choices: tuple[str, ...] = ()

    @property
    def signature(self) -> str:
        """How the prop is advertised in the prompt fragment."""
        if self.kind is PropKind.ENUM:
            return f"{self.name}: " + "|".join(f'"{c}"' for c in self.choices)
        if self.kind is PropKind.REFS:
            return f"{self.name}: [id, ...]"
        return f"{self.name}: {self.kind.value}"


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    name: str
    purpose: str
    props: tuple[PropSpec, ...]
    #: ``root`` must be a container (contract rule 1, §5.2).
    is_container: bool = False
    #: ``Markdown`` is reachable from ``fallback_seed`` only; the LLM cannot emit it.
    llm_emittable: bool = True

    @property
    def prop_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.props)

    @property
    def children_prop(self) -> PropSpec | None:
        for prop in self.props:
            if prop.kind is PropKind.REFS:
                return prop
        return None

    @property
    def value_props(self) -> tuple[PropSpec, ...]:
        """Props that live in ``Component.props`` (everything but the refs array)."""
        return tuple(p for p in self.props if p.kind is not PropKind.REFS)

    def prop(self, name: str) -> PropSpec | None:
        for prop in self.props:
            if prop.name == name:
                return prop
        return None

    @property
    def signature(self) -> str:
        """``Chart(kind: "bar"|"line", title: string, ...)`` — used by the prompt."""
        return f"{self.name}(" + ", ".join(p.signature for p in self.props) + ")"


@dataclass(frozen=True, slots=True)
class UIKit:
    components: tuple[ComponentSpec, ...]

    def get(self, name: str) -> ComponentSpec | None:
        for component in self.components:
            if component.name == name:
                return component
        return None

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.components)

    @property
    def llm_components(self) -> tuple[ComponentSpec, ...]:
        return tuple(c for c in self.components if c.llm_emittable)

    @property
    def llm_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.llm_components)

    @property
    def container_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.components if c.is_container)


# --------------------------------------------------------------------------------------
# The frozen catalogue. Order of the tuple = order of the table in §5.3.
# Order of ``props`` = the positional argument order of the OpenUI dialect (§5.4).
# --------------------------------------------------------------------------------------

UI_KIT = UIKit(
    components=(
        ComponentSpec(
            name="Stack",
            purpose="Contenedor vertical",
            is_container=True,
            props=(
                PropSpec("children", PropKind.REFS, "Ids de los bloques hijos, en orden"),
                PropSpec("gap", PropKind.ENUM, "Separacion vertical", GAP_VALUES),
            ),
        ),
        ComponentSpec(
            name="TextContent",
            purpose="Prosa",
            props=(
                PropSpec("text", PropKind.STRING, "Texto plano o marcado inline"),
                PropSpec("variant", PropKind.ENUM, "Rol del texto", TEXT_VARIANTS),
            ),
        ),
        ComponentSpec(
            name="Card",
            purpose="Agrupar",
            is_container=True,
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del grupo"),
                PropSpec("children", PropKind.REFS, "Ids de los bloques agrupados"),
            ),
        ),
        ComponentSpec(
            name="Callout",
            purpose="Regla critica, excepcion",
            props=(
                PropSpec("tone", PropKind.ENUM, "Intencion del aviso", CALLOUT_TONES),
                PropSpec("text", PropKind.STRING, "Texto del aviso"),
            ),
        ),
        ComponentSpec(
            name="StepSequence",
            purpose="Procedimiento (2-7 pasos)",
            props=(
                PropSpec("title", PropKind.STRING, "Nombre del procedimiento"),
                PropSpec("steps", PropKind.STRING_LIST, "Un paso por elemento"),
            ),
        ),
        ComponentSpec(
            name="Table",
            purpose="Comparar conceptos",
            props=(
                PropSpec("headers", PropKind.STRING_LIST, "Cabeceras de columna"),
                PropSpec("rows", PropKind.STRING_MATRIX, "Filas: array de arrays de texto"),
            ),
        ),
        ComponentSpec(
            name="CodeBlock",
            purpose="Ejemplo de codigo",
            props=(
                PropSpec("language", PropKind.STRING, "Lenguaje, en minusculas"),
                PropSpec("code", PropKind.STRING, "Codigo, con \\n para los saltos"),
            ),
        ),
        ComponentSpec(
            name="Chart",
            purpose="Dato cuantitativo",
            props=(
                PropSpec("kind", PropKind.ENUM, "Tipo de grafico", CHART_KINDS),
                PropSpec("title", PropKind.STRING, "Titulo del grafico"),
                PropSpec("labels", PropKind.STRING_LIST, "Etiqueta por valor"),
                PropSpec("values", PropKind.NUMBER_LIST, "Un numero por etiqueta"),
            ),
        ),
        ComponentSpec(
            name="QuizItem",
            purpose="Ejercicio",
            props=(
                PropSpec("item_id", PropKind.STRING, "Id corto y unico dentro del spec"),
                PropSpec("item_type", PropKind.ENUM, "Tipo de ejercicio", ITEM_TYPES),
                PropSpec("bloom_level", PropKind.ENUM, "Nivel cognitivo", BLOOM_LEVELS),
                PropSpec("question", PropKind.STRING, "Enunciado"),
                PropSpec("options", PropKind.STRING_LIST, "Opciones; [] si no aplica"),
            ),
        ),
        ComponentSpec(
            name="Markdown",
            purpose="Solo para fallback_seed; el modelo no puede emitirlo",
            llm_emittable=False,
            props=(PropSpec("content", PropKind.STRING, "Contenido de la leccion semilla"),),
        ),
    )
)

COMPONENT_NAMES: tuple[str, ...] = UI_KIT.names
LLM_COMPONENT_NAMES: tuple[str, ...] = UI_KIT.llm_names
CONTAINER_NAMES: tuple[str, ...] = UI_KIT.container_names

__all__ = [
    "BLOOM_LEVELS",
    "CALLOUT_TONES",
    "CHART_KINDS",
    "COMPONENT_NAMES",
    "CONTAINER_NAMES",
    "GAP_VALUES",
    "ITEM_TYPES",
    "LEAD_VARIANT",
    "LLM_COMPONENT_NAMES",
    "TEXT_VARIANTS",
    "UI_KIT",
    "ComponentSpec",
    "PropKind",
    "PropSpec",
    "UIKit",
]
