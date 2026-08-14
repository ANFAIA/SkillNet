/**
 * The SkillNet UI Kit registered with OpenUI's own component mechanism (§5.3).
 *
 * ## Why the dependency is here at all (AGENTS.md: no new dependency without a
 * justification)
 *
 * `@openuidev/react-lang` (+ `@openuidev/lang-core`, + `zod` as its peer)
 * replaces a hand-written parser *and* a hand-written tree walk with
 * the reference implementation of the dialect we already emit. Measured before
 * adopting it: our ten components and their positional order are declarable in
 * the vendor's `defineComponent` with **no concession**, and the vendor parser
 * accepts all ten valid `.openui` fixtures of the backend with `meta.errors ==
 * []`. It also brings two things we did not have: a per-node `partial` flag and
 * `meta.unresolved`, i.e. real streaming instead of "drop the half-written line".
 *
 * What it does NOT bring: validation. `zod` here is a *description* the parser
 * never evaluates (see `schemas.ts`), and none of the seven contract rules of
 * §5.2 are its business. The backend validator stays.
 *
 * `@modelcontextprotocol/sdk` is declared as an OPTIONAL peer and is imported by
 * neither bundle (measured: static imports are `zod/v4` + `zod/v4/core` for
 * lang-core, and `@openuidev/lang-core` + `react` + `react/jsx-runtime` for
 * react-lang). It is deliberately NOT installed.
 *
 * Versions are pinned exactly — no `^`. The security properties this migration
 * relies on (no `fetch`/`eval`/`window.open` anywhere in the bundles, `@OpenUrl`
 * delegated to a prop we do not pass, `Query`/`Mutation` reachable only through a
 * `toolProvider` we do not pass) are implementation details of 0.2.10/0.2.9, not
 * a published contract. A minor bump can change them silently — which is also why
 * `@openuidev/lang-core` is a DIRECT dependency at `0.2.10` even though nothing
 * here imports it: react-lang depends on it as `^0.2.10`, so leaving it transitive
 * would let the audited half of the bundle float on the next `pnpm install`. It is
 * also what lets the build-time `prompt-catalog.mjs` resolve it from Node.
 *
 * ## The renderers are the blocks that already exist
 *
 * Every `component` below is an adapter over `blocks/*.tsx`, untouched. The
 * design system, the §8.5 `data-no-explain` markers and the SVG chart are all
 * preserved; the only new code is the prop hand-off.
 */

import type { ReactNode } from 'react'
import { createLibrary, defineComponent } from '@openuidev/react-lang'
import type { ComponentRenderProps } from '@openuidev/react-lang'

import {
  AudioExplanationBlock,
  BeforeAfterBlock,
  CalloutBlock,
  CardBlock,
  ChartBlock,
  CodeBlockBlock,
  DragOrderBlock,
  MarkdownBlock,
  PronunciationExerciseBlock,
  FlashcardBlock,
  HintRevealBlock,
  DidactGlossaryBlock,
  DidactTimelineBlock,
  DidactWorkedExampleBlock,
  LearningExperience,
  StackBlock,
  StackItem,
  StepSequenceBlock,
  TableBlock,
  TextContentBlock,
} from '../blocks'
import {
  readChildren,
  readEnum,
  readNumberArray,
  readString,
  readStringArray,
  readStringMatrix,
} from './coerce'
import { QuizItemRenderer } from './QuizItemRenderer'
import { hasSolvableItem } from './solvableSteps'
import {
  CALLOUT_TONES,
  CHART_KINDS,
  KIT_DESCRIPTIONS,
  STACK_GAPS,
  TEXT_VARIANTS,
  VOICE_STYLES,
  audioExplanationProps,
  beforeAfterProps,
  calloutProps,
  cardProps,
  chartProps,
  codeBlockProps,
  dragOrderProps,
  markdownProps,
  pronunciationExerciseProps,
  flashcardProps,
  hintRevealProps,
  didactGlossaryProps,
  didactTimelineProps,
  didactWorkedExampleProps,
  didactActivityProps,
  learningExperienceProps,
  quizItemProps,
  stackProps,
  stepSequenceProps,
  tableProps,
  textContentProps,
} from './schemas'

/** `renderNode` already flattens arrays and drops nulls, so children go in whole. */
function renderKids(
  renderNode: (value: unknown) => ReactNode,
  children: unknown,
): ReactNode {
  return renderNode(readChildren(children))
}

/**
 * El unico contenedor que NO usa `renderKids`: sus hijos se rinden de uno en uno para
 * poder etiquetar cada uno con si lleva un ejercicio dentro. Cuando este `Stack` es la
 * raiz de una leccion, cada hijo es un paso del stepper, y el stepper necesita esa
 * etiqueta en render —no un frame despues— para no enseñar el boton de nodo siguiente
 * encima de un ejercicio sin resolver. Ver `solvableSteps.ts` y `blocks/StackBlock.tsx`.
 */
const Stack = defineComponent({
  name: 'Stack',
  description: KIT_DESCRIPTIONS.Stack,
  props: stackProps,
  component: ({ props, renderNode }: ComponentRenderProps<{ children: unknown[]; gap: string }>) => (
    <StackBlock gap={readEnum(props.gap, STACK_GAPS, 'md')}>
      {readChildren(props.children).map((child, i) => (
        <StackItem key={i} solvable={hasSolvableItem(child)}>
          {renderNode(child)}
        </StackItem>
      ))}
    </StackBlock>
  ),
})

const TextContent = defineComponent({
  name: 'TextContent',
  description: KIT_DESCRIPTIONS.TextContent,
  props: textContentProps,
  component: ({ props }: ComponentRenderProps<{ text: string; variant: string }>) => (
    <TextContentBlock
      text={readString(props.text)}
      variant={readEnum(props.variant, TEXT_VARIANTS, 'body')}
    />
  ),
})

const Card = defineComponent({
  name: 'Card',
  description: KIT_DESCRIPTIONS.Card,
  props: cardProps,
  component: ({ props, renderNode }: ComponentRenderProps<{ title: string; children: unknown[] }>) => (
    <CardBlock title={readString(props.title)}>
      {renderKids(renderNode, props.children)}
    </CardBlock>
  ),
})

const Callout = defineComponent({
  name: 'Callout',
  description: KIT_DESCRIPTIONS.Callout,
  props: calloutProps,
  component: ({ props }: ComponentRenderProps<{ tone: string; text: string }>) => (
    <CalloutBlock
      tone={readEnum(props.tone, CALLOUT_TONES, 'info')}
      text={readString(props.text)}
    />
  ),
})

const StepSequence = defineComponent({
  name: 'StepSequence',
  description: KIT_DESCRIPTIONS.StepSequence,
  props: stepSequenceProps,
  component: ({ props }: ComponentRenderProps<{ title: string; steps: string[] }>) => (
    <StepSequenceBlock
      title={readString(props.title)}
      steps={readStringArray(props.steps)}
    />
  ),
})

const Table = defineComponent({
  name: 'Table',
  description: KIT_DESCRIPTIONS.Table,
  props: tableProps,
  component: ({ props }: ComponentRenderProps<{ headers: string[]; rows: string[][] }>) => (
    <TableBlock
      headers={readStringArray(props.headers)}
      rows={readStringMatrix(props.rows)}
    />
  ),
})

const CodeBlock = defineComponent({
  name: 'CodeBlock',
  description: KIT_DESCRIPTIONS.CodeBlock,
  props: codeBlockProps,
  component: ({ props }: ComponentRenderProps<{ language: string; code: string }>) => (
    <CodeBlockBlock language={readString(props.language)} code={readString(props.code)} />
  ),
})

const Chart = defineComponent({
  name: 'Chart',
  description: KIT_DESCRIPTIONS.Chart,
  props: chartProps,
  component: ({
    props,
  }: ComponentRenderProps<{ kind: string; title: string; labels: string[]; values: number[] }>) => (
    <ChartBlock
      kind={readEnum(props.kind, CHART_KINDS, 'bar')}
      title={readString(props.title)}
      labels={readStringArray(props.labels)}
      values={readNumberArray(props.values)}
    />
  ),
})

/** Lives in its own file because it is the only renderer that calls a hook. */
const QuizItem = defineComponent({
  name: 'QuizItem',
  description: KIT_DESCRIPTIONS.QuizItem,
  props: quizItemProps,
  component: QuizItemRenderer,
})

const BeforeAfter = defineComponent({
  name: 'BeforeAfter',
  description: KIT_DESCRIPTIONS.BeforeAfter,
  props: beforeAfterProps,
  component: ({
    props,
  }: ComponentRenderProps<{
    title: string
    beforeLabel: string
    beforeContent: string
    afterLabel: string
    afterContent: string
  }>) => (
    <BeforeAfterBlock
      title={readString(props.title)}
      beforeLabel={readString(props.beforeLabel, 'Antes')}
      beforeContent={readString(props.beforeContent)}
      afterLabel={readString(props.afterLabel, 'Despues')}
      afterContent={readString(props.afterContent)}
    />
  ),
})

/**
 * `fallback_seed` only (§5.3). It is registered because the "never a red screen"
 * path serves `lessons.content` through this same renderer; it is absent from the
 * prompt catalogue in Python, so the model is never taught to emit it.
 */
const Markdown = defineComponent({
  name: 'Markdown',
  description: KIT_DESCRIPTIONS.Markdown,
  props: markdownProps,
  component: ({ props }: ComponentRenderProps<{ content: string }>) => (
    <MarkdownBlock content={readString(props.content)} />
  ),
})

const DragOrder = defineComponent({
  name: 'DragOrder',
  description: KIT_DESCRIPTIONS.DragOrder,
  props: dragOrderProps,
  component: ({ props }: ComponentRenderProps<{ instruction: string; items: string[]; correctOrder: string[] }>) => (
    <DragOrderBlock
      instruction={readString(props.instruction)}
      items={readStringArray(props.items)}
      correctOrder={readStringArray(props.correctOrder)}
    />
  ),
})

const AudioExplanation = defineComponent({
  name: 'AudioExplanation',
  description: KIT_DESCRIPTIONS.AudioExplanation,
  props: audioExplanationProps,
  component: ({ props }: ComponentRenderProps<{ text: string; voice: string }>) => (
    <AudioExplanationBlock
      text={readString(props.text)}
      voice={readEnum(props.voice, VOICE_STYLES, 'neutral')}
    />
  ),
})

const PronunciationExercise = defineComponent({
  name: 'PronunciationExercise',
  description: KIT_DESCRIPTIONS.PronunciationExercise,
  props: pronunciationExerciseProps,
  component: ({ props }: ComponentRenderProps<{ targetText: string; language: string }>) => (
    <PronunciationExerciseBlock
      targetText={readString(props.targetText)}
      language={readString(props.language, 'es')}
    />
  ),
})

const Flashcard = defineComponent({
  name: 'Flashcard',
  description: KIT_DESCRIPTIONS.Flashcard,
  props: flashcardProps,
  component: ({ props }: ComponentRenderProps<{ front: string; back: string }>) => (
    <FlashcardBlock front={readString(props.front)} back={readString(props.back)} />
  ),
})

const HintReveal = defineComponent({
  name: 'HintReveal',
  description: KIT_DESCRIPTIONS.HintReveal,
  props: hintRevealProps,
  component: ({ props }: ComponentRenderProps<{ title: string; hints: string[]; solution: string }>) => (
    <HintRevealBlock title={readString(props.title)} hints={readStringArray(props.hints)} solution={readString(props.solution)} />
  ),
})

const DidactGlossary = defineComponent({
  name: 'DidactGlossary', description: KIT_DESCRIPTIONS.DidactGlossary, props: didactGlossaryProps,
  component: ({ props }: ComponentRenderProps<{ title: string; terms: string[]; definitions: string[] }>) => (
    <DidactGlossaryBlock title={readString(props.title)} terms={readStringArray(props.terms)} definitions={readStringArray(props.definitions)} />
  ),
})
const DidactTimeline = defineComponent({
  name: 'DidactTimeline', description: KIT_DESCRIPTIONS.DidactTimeline, props: didactTimelineProps,
  component: ({ props }: ComponentRenderProps<{ label: string; steps: string[]; details: string[] }>) => (
    <DidactTimelineBlock label={readString(props.label)} steps={readStringArray(props.steps)} details={readStringArray(props.details)} />
  ),
})
const DidactWorkedExample = defineComponent({
  name: 'DidactWorkedExample', description: KIT_DESCRIPTIONS.DidactWorkedExample, props: didactWorkedExampleProps,
  component: ({ props }: ComponentRenderProps<{ problem: string; steps: string[]; summary: string }>) => (
    <DidactWorkedExampleBlock problem={readString(props.problem)} steps={readStringArray(props.steps)} summary={readString(props.summary)} />
  ),
})
const DidactActivity = defineComponent({
  name: 'DidactActivity', description: KIT_DESCRIPTIONS.DidactActivity, props: didactActivityProps,
  component: ({ props }: ComponentRenderProps<{ activity_id: string; component_id: string }>) => (
    <LearningExperience
      experienceId={readString(props.activity_id)}
      implementationRef={`${readString(props.component_id)}@1`}
      definitionRef={readString(props.activity_id)}
      activityId={readString(props.activity_id)}
      componentId={readString(props.component_id)}
    />
  ),
})
const LearningExperienceComponent = defineComponent({
  name: 'LearningExperience',
  description: KIT_DESCRIPTIONS.LearningExperience,
  props: learningExperienceProps,
  component: ({ props }: ComponentRenderProps<{
    experience_id: string
    implementation_ref: string
    definition_ref: string
  }>) => (
    <LearningExperience
      experienceId={readString(props.experience_id)}
      implementationRef={readString(props.implementation_ref)}
      definitionRef={readString(props.definition_ref)}
    />
  ),
})
/**
 * The render library.
 *
 * `root: 'Stack'` is contract rule 1 (§5.2) as far as the vendor can express it:
 * it is the component a bare program is resolved against. The other six rules
 * are NOT expressible here — see `assertStaticOnly.ts` for the two that survive
 * as structural checks, and `src/render/spec.py` for all seven.
 *
 * A component that is not in this record is never painted: the runtime does
 * `library.components[typeName]?.component` and returns `null` when it misses,
 * while the parser reports `unknown-component` for the repair loop.
 */
export const skillnetLibrary = createLibrary({
  id: 'skillnet-ui/1',
  root: 'Stack',
  components: [
    Stack,
    TextContent,
    Card,
    Callout,
    StepSequence,
    Table,
    CodeBlock,
    Chart,
    QuizItem,
    BeforeAfter,
    Markdown,
    DragOrder,
    AudioExplanation,
    PronunciationExercise,
    Flashcard,
    HintReveal,
    DidactGlossary,
    DidactTimeline,
    DidactWorkedExample,
    LearningExperienceComponent,
    DidactActivity,
  ],
})

/** `library.toJSONSchema()` is what the parser actually compiles; cached once. */
export const skillnetLibrarySchema = skillnetLibrary.toJSONSchema()
