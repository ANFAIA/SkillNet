"""The SkillNet UI Kit — the frozen catalogue of §5.3, validator side.

This module is the source of truth for **validation**: the component list, the exact
prop names, the value types, the closed enums and the *positional* order the OpenUI
dialect uses. ``src/render/spec.py`` enforces all of it, and the OpenUI parser cannot:
``compileSchema()`` keeps only ``{name, required, defaultValue}``, so their parser checks
arity and presence and nothing else.

Since 2026-07-26 it is **no longer** where the prompt comes from. The prompt is generated
by ``library.prompt()`` from the frontend kit
(``apps/skillnet-web/src/components/courses/kit/``) into the artefacts that
``src/render/prompt.py`` reads. The two catalogues are kept honest by a hash rather than
by discipline: ``prompt.catalog_digest_from_kit()`` recomputes the normalised catalogue
from this file and ``tests/test_render_prompt_artifact.py`` fails when it stops matching
the artefact. Change the components here and the drift test tells you to regenerate;
change them there and it tells you to update this file.

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
VOICE_STYLES: tuple[str, ...] = ("neutral", "warm", "formal")
ITEM_TYPES: tuple[str, ...] = tuple(m.value for m in ExerciseType)

#: The ``variant`` a ``TextContent`` must carry to satisfy contract rule 7 (§5.2).
LEAD_VARIANT = "lead"


class PropKind(str, enum.Enum):
    """The value shapes the dialect can express."""

    STRING = "string"
    NUMBER = "number"
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
            name="SliderExploration",
            purpose="Explorar un parametro con slider interactivo",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del explorador"),
                PropSpec("variable", PropKind.STRING, "Nombre de la variable"),
                PropSpec("min", PropKind.NUMBER, "Valor minimo del slider"),
                PropSpec("max", PropKind.NUMBER, "Valor maximo del slider"),
                PropSpec("step", PropKind.NUMBER, "Incremento del slider"),
                PropSpec(
                    "formula", PropKind.STRING,
                    'Formula con la variable, p.ej. "y = 2 * x + 3"',
                ),
                PropSpec("description", PropKind.STRING, "Texto explicativo"),
            ),
        ),
        ComponentSpec(
            name="ManipulableGraph",
            purpose="Plano cartesiano interactivo con puntos y funciones",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del grafico"),
                PropSpec("xLabel", PropKind.STRING, "Etiqueta del eje X"),
                PropSpec("yLabel", PropKind.STRING, "Etiqueta del eje Y"),
                PropSpec("points", PropKind.STRING_MATRIX, "Puntos: [label, x, y, draggable?]"),
                PropSpec(
                    "functions", PropKind.STRING_LIST,
                    'Funciones matematicas, p.ej. "Math.sin(x)"',
                ),
            ),
        ),
        ComponentSpec(
            name="BeforeAfter",
            purpose="Comparar dos estados con divisor deslizante",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo de la comparacion"),
                PropSpec("beforeLabel", PropKind.STRING, "Etiqueta del estado anterior"),
                PropSpec("beforeContent", PropKind.STRING, "Contenido del estado anterior"),
                PropSpec("afterLabel", PropKind.STRING, "Etiqueta del estado posterior"),
                PropSpec("afterContent", PropKind.STRING, "Contenido del estado posterior"),
            ),
        ),
        ComponentSpec(
            name="Markdown",
            purpose="Solo para fallback_seed; el modelo no puede emitirlo",
            llm_emittable=False,
            props=(PropSpec("content", PropKind.STRING, "Contenido de la leccion semilla"),),
        ),
        ComponentSpec(
            name="DragOrder",
            purpose="Reordenar arrastrando",
            props=(
                PropSpec("instruction", PropKind.STRING, "Enunciado de la tarea de ordenar"),
                PropSpec("items", PropKind.STRING_LIST, "Elementos a ordenar (desordenados)"),
                PropSpec("correctOrder", PropKind.STRING_LIST, "Secuencia correcta"),
            ),
        ),
        ComponentSpec(
            name="HotspotImage",
            purpose="Imagen con zonas interactivas",
            props=(
                PropSpec("imageUrl", PropKind.STRING, "URL de la imagen"),
                PropSpec("alt", PropKind.STRING, "Texto alternativo"),
                PropSpec(
                    "hotspots", PropKind.STRING_MATRIX,
                    "Puntos: [[x, y, label, detail], ...]",
                ),
            ),
        ),
        ComponentSpec(
            name="StepByStepReveal",
            purpose="Revelacion progresiva de pasos",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del bloque"),
                PropSpec("steps", PropKind.STRING_MATRIX, "Pasos: [[enunciado, explicacion], ...]"),
            ),
        ),
        ComponentSpec(
            name="AudioExplanation",
            purpose="Texto leido en voz alta con resaltado de palabras",
            props=(
                PropSpec("text", PropKind.STRING, "Texto que se leera en voz alta"),
                PropSpec("voice", PropKind.ENUM, "Estilo de voz", VOICE_STYLES),
            ),
        ),
        ComponentSpec(
            name="PronunciationExercise",
            purpose="Escuchar y practicar pronunciacion con comparacion de ondas",
            props=(
                PropSpec("targetText", PropKind.STRING, "Texto objetivo para practicar"),
                PropSpec("language", PropKind.STRING, "Codigo de idioma, p.ej. \"es\""),
            ),
        ),
        ComponentSpec(
            name="DiagramBuilder",
            purpose="Diagrama SVG que se construye paso a paso",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del diagrama"),
                PropSpec(
                    "steps", PropKind.STRING_MATRIX,
                    "Pasos: [[etiqueta, svgFragment, explicacion], ...]",
                ),
            ),
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
    "VOICE_STYLES",
    "ComponentSpec",
    "PropKind",
    "PropSpec",
    "UIKit",
]
