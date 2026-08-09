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


class ContentFunction(str, enum.Enum):
    """What a piece of source material *does*, independent of which block renders it.

    The layer `docs/design/arquitectura-componentes-funcional.md` introduces: a detector
    says "this enumerates", not "use a Table". The mapping to blocks lives in the
    components themselves (``ComponentSpec.functions``), so adding a component becomes a
    local edit instead of teaching ``shape.py`` one more name.

    Only ENUMERAR, PROCEDIMENTAR and CUANTIFICAR are reachable today: they are what the
    four detectors of ``shape.py`` emit. The rest are declared so components can already
    claim them, but nothing routes there until a detector or a classifier does (phases 3
    and 4). A function no detector emits is dead weight in the registry, not a bug.
    """

    ENUMERAR = "enumerar"
    PROCEDIMENTAR = "procedimentar"
    CUANTIFICAR = "cuantificar"
    CONTRASTAR = "contrastar"
    VARIAR = "variar"
    EXPLORAR = "explorar"
    LOCALIZAR = "localizar"
    EVALUAR = "evaluar"


@dataclass(frozen=True, slots=True)
class FunctionFit:
    """A component's claim on one function, and how strongly it wants it.

    ``rank`` breaks ties, lower first. It belongs to the *pair* and not to the component
    because a block can be the obvious answer for one function and the fallback for
    another: ``Table`` is the default for ENUMERAR and a poor second for CONTRASTAR.
    """

    function: ContentFunction
    rank: int = 50


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
    #: The functions this component competes for. Empty = it is never proposed by the
    #: function layer and can only arrive by an explicit rule in a prompt.
    functions: tuple[FunctionFit, ...] = ()

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

    def candidates_for(self, function: ContentFunction) -> tuple[str, ...]:
        """Components that claim ``function``, best first.

        The registry lookup that replaces the block name hard-coded in ``shape.py``.
        Ties break on catalogue order, so the result is deterministic and a component
        added at the end never displaces an incumbent by accident.
        """
        claims = [
            (fit.rank, index, component.name)
            for index, component in enumerate(self.components)
            for fit in component.functions
            if fit.function is function and component.llm_emittable
        ]
        return tuple(name for _, _, name in sorted(claims))

    def primary_for(self, function: ContentFunction) -> str:
        """The component a function resolves to when nobody declines. ``""`` if none."""
        candidates = self.candidates_for(function)
        return candidates[0] if candidates else ""


# --------------------------------------------------------------------------------------
# The frozen catalogue. Order of the tuple = order of the table in §5.3.
# Order of ``props`` = the positional argument order of the OpenUI dialect (§5.4).
# --------------------------------------------------------------------------------------

UI_KIT = UIKit(
    components=(
        ComponentSpec(
            name="Stack",
            purpose="Contenedor vertical. Envuelve la pantalla entera; siempre es el root",
            is_container=True,
            props=(
                PropSpec("children", PropKind.REFS, "Ids de los bloques hijos, en orden"),
                PropSpec("gap", PropKind.ENUM, "Separacion vertical", GAP_VALUES),
            ),
        ),
        ComponentSpec(
            name="TextContent",
            purpose="Prosa breve: el gancho inicial o una transicion. No vuelques aqui el contenido",
            props=(
                PropSpec("text", PropKind.STRING, "Texto plano o marcado inline"),
                PropSpec("variant", PropKind.ENUM, "Rol del texto", TEXT_VARIANTS),
            ),
        ),
        ComponentSpec(
            name="Card",
            functions=(FunctionFit(ContentFunction.ENUMERAR, 60), FunctionFit(ContentFunction.VARIAR, 40)),
            purpose="Agrupa bajo un titulo propio un caso practico o un ejemplo cerrado",
            is_container=True,
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del grupo"),
                PropSpec("children", PropKind.REFS, "Ids de los bloques agrupados"),
            ),
        ),
        ComponentSpec(
            name="Callout",
            functions=(FunctionFit(ContentFunction.CONTRASTAR, 70),),
            purpose="Una regla critica o excepcion que no se puede pasar por alto. Uno por pantalla",
            props=(
                PropSpec("tone", PropKind.ENUM, "Intencion del aviso", CALLOUT_TONES),
                PropSpec("text", PropKind.STRING, "Texto del aviso"),
            ),
        ),
        ComponentSpec(
            name="StepSequence",
            functions=(FunctionFit(ContentFunction.PROCEDIMENTAR, 10),),
            purpose="Pasos en orden que se entienden solos. Prefierelo con 3-7 pasos cortos",
            props=(
                PropSpec("title", PropKind.STRING, "Nombre del procedimiento"),
                PropSpec("steps", PropKind.STRING_LIST, "Un paso por elemento"),
            ),
        ),
        ComponentSpec(
            name="Table",
            functions=(FunctionFit(ContentFunction.ENUMERAR, 10), FunctionFit(ContentFunction.CUANTIFICAR, 10), FunctionFit(ContentFunction.CONTRASTAR, 60)),
            purpose="Varios elementos comparados por varios atributos. Si solo contrastas DOS estados usa BeforeAfter",
            props=(
                PropSpec("headers", PropKind.STRING_LIST, "Cabeceras de columna"),
                PropSpec("rows", PropKind.STRING_MATRIX, "Filas: array de arrays de texto"),
            ),
        ),
        ComponentSpec(
            name="CodeBlock",
            purpose="Fragmento de codigo de ejemplo",
            props=(
                PropSpec("language", PropKind.STRING, "Lenguaje, en minusculas"),
                PropSpec("code", PropKind.STRING, "Codigo, con \\n para los saltos"),
            ),
        ),
        ComponentSpec(
            name="Chart",
            functions=(FunctionFit(ContentFunction.CUANTIFICAR, 20),),
            purpose="Cifras comparables entre categorias. Solo si las cifras estan en la fuente",
            props=(
                PropSpec("kind", PropKind.ENUM, "Tipo de grafico", CHART_KINDS),
                PropSpec("title", PropKind.STRING, "Titulo del grafico"),
                PropSpec("labels", PropKind.STRING_LIST, "Etiqueta por valor"),
                PropSpec("values", PropKind.NUMBER_LIST, "Un numero por etiqueta"),
            ),
        ),
        ComponentSpec(
            name="QuizItem",
            functions=(FunctionFit(ContentFunction.EVALUAR, 10),),
            purpose="Pregunta de evaluacion sobre un caso concreto",
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
            functions=(FunctionFit(ContentFunction.EXPLORAR, 10),),
            purpose="El aprendiz mueve una variable y ve como cambia el resultado. Requiere una relacion causa-efecto enunciada en la fuente",
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
            functions=(FunctionFit(ContentFunction.EXPLORAR, 20),),
            purpose="Plano cartesiano donde el aprendiz mueve puntos o funciones",
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
            functions=(FunctionFit(ContentFunction.CONTRASTAR, 10),),
            purpose="Contrasta exactamente DOS estados: correcto frente a incorrecto, antes frente a despues. Prefierelo a Table cuando la comparacion es de dos",
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
            functions=(FunctionFit(ContentFunction.EVALUAR, 20),),
            purpose="Evaluar reordenando pasos o prioridades arrastrando",
            props=(
                PropSpec("instruction", PropKind.STRING, "Enunciado de la tarea de ordenar"),
                PropSpec("items", PropKind.STRING_LIST, "Elementos a ordenar (desordenados)"),
                PropSpec("correctOrder", PropKind.STRING_LIST, "Secuencia correcta"),
            ),
        ),
        ComponentSpec(
            name="HotspotImage",
            functions=(FunctionFit(ContentFunction.LOCALIZAR, 10),),
            purpose="Marcar zonas sobre una imagen. Requiere una URL de imagen real; no lo uses si no la hay",
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
            functions=(FunctionFit(ContentFunction.PROCEDIMENTAR, 20),),
            purpose="Procedimiento cuyos pasos necesitan explicacion propia. Prefierelo a StepSequence cuando un paso no se entiende solo",
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
            purpose="Escuchar y practicar la pronunciacion de un termino",
            props=(
                PropSpec("targetText", PropKind.STRING, "Texto objetivo para practicar"),
                PropSpec("language", PropKind.STRING, "Codigo de idioma, p.ej. \"es\""),
            ),
        ),
        ComponentSpec(
            name="DiagramBuilder",
            functions=(FunctionFit(ContentFunction.PROCEDIMENTAR, 60),),
            purpose="Diagrama que se dibuja paso a paso para mostrar como se relacionan las partes",
            props=(
                PropSpec("title", PropKind.STRING, "Titulo del diagrama"),
                PropSpec(
                    "steps", PropKind.STRING_MATRIX,
                    "Pasos: [[etiqueta, svgFragment, explicacion], ...]",
                ),
            ),
        ),
        ComponentSpec(
            name="Accordion",
            functions=(FunctionFit(ContentFunction.VARIAR, 20),),
            purpose="Excepciones o detalles que no todo el mundo necesita leer",
            is_container=True,
            props=(
                PropSpec("children", PropKind.REFS, "Ids de los AccordionItem hijos"),
            ),
        ),
        ComponentSpec(
            name="AccordionItem",
            purpose="Seccion plegable dentro de Accordion",
            is_container=True,
            props=(
                PropSpec("trigger", PropKind.STRING, "Titulo de la seccion plegable"),
                PropSpec("children", PropKind.REFS, "Ids de los bloques de contenido"),
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
