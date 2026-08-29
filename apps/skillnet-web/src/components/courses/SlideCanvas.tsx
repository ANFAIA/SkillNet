import {
  CalloutBlock,
  CardBlock,
  ChartBlock,
  DidactTimelineBlock,
  StepSequenceBlock,
  TableBlock,
  TextContentBlock,
} from './blocks'

export type SlideComposition =
  | 'auto'
  | 'cover'
  | 'statement'
  | 'split'
  | 'process'
  | 'timeline'
  | 'grid'
  | 'comparison'
  | 'data'

export type SlideBlockSpec =
  | { type: 'text'; text: string; variant?: 'body' | 'lead' | 'caption' }
  | { type: 'callout'; tone?: 'info' | 'warn' | 'success'; text: string }
  | { type: 'steps'; title: string; steps: string[] }
  | { type: 'timeline'; label: string; steps: string[]; details: string[] }
  | { type: 'card'; title: string; text: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'chart'; kind?: 'bar' | 'line'; title: string; labels: string[]; values: number[] }

export interface SlideCanvasSpec {
  title: string
  subtitle?: string | null
  composition?: SlideComposition
  visual_brief?: string | null
  blocks: SlideBlockSpec[]
}

export interface SlideCanvasProps {
  slide: SlideCanvasSpec
  /** A decorative, text-free illustration generated for this card. */
  imageUrl?: string
}

function inferComposition(slide: SlideCanvasSpec): Exclude<SlideComposition, 'auto'> {
  if (slide.composition && slide.composition !== 'auto') return slide.composition
  if (slide.blocks.some((block) => block.type === 'steps')) return 'process'
  if (slide.blocks.some((block) => block.type === 'timeline')) return 'timeline'
  if (slide.blocks.filter((block) => block.type === 'card').length > 1) return 'grid'
  if (slide.blocks.some((block) => block.type === 'chart' || block.type === 'table')) return 'data'
  if (slide.blocks.length > 1) return 'split'
  return 'statement'
}

function SlideBlock({ block }: { block: SlideBlockSpec }) {
  switch (block.type) {
    case 'text':
      return <TextContentBlock text={block.text} variant={block.variant ?? 'body'} />
    case 'callout':
      return <CalloutBlock tone={block.tone ?? 'info'} text={block.text} />
    case 'steps':
      return <StepSequenceBlock title={block.title} steps={block.steps ?? []} />
    case 'timeline':
      return (
        <DidactTimelineBlock
          label={block.label}
          steps={block.steps ?? []}
          details={block.details ?? []}
        />
      )
    case 'card':
      return (
        <CardBlock title={block.title}>
          <TextContentBlock text={block.text} variant="body" />
        </CardBlock>
      )
    case 'table':
      return <TableBlock headers={block.headers ?? []} rows={block.rows ?? []} />
    case 'chart':
      return (
        <ChartBlock
          kind={block.kind ?? 'bar'}
          title={block.title}
          labels={block.labels ?? []}
          values={block.values ?? []}
        />
      )
    default:
      return null
  }
}

function Illustration({ src }: { src: string }) {
  return (
    <div className="flex h-full min-h-40 items-center justify-center overflow-hidden bg-bg-subtle">
      <img
        src={src}
        alt=""
        className="h-full w-full object-contain p-8 grayscale contrast-125 @lg:p-10"
      />
    </div>
  )
}

function Blocks({ blocks, columns = false }: { blocks: SlideBlockSpec[]; columns?: boolean }) {
  return (
    // Two-up only once the slide itself is wide enough to give each column a real measure.
    // At the width the deck actually gets inside a modal (~560 px) a second column left a
    // table with ~260 px for three columns, which is how "Tecnica" became "Tec / nic / a".
    <div className={columns ? 'grid min-w-0 gap-4 @2xl:grid-cols-2' : 'min-w-0 space-y-4'}>
      {blocks.map((block, index) => (
        <div key={index} className="min-w-0">
          <SlideBlock block={block} />
        </div>
      ))}
    </div>
  )
}

/**
 * Slide renderer: the model chooses a semantic composition, while SkillNet owns every pixel
 * of typography, spacing and data rendering. Generated imagery is always a supporting
 * ingredient and never replaces the structured slide.
 *
 * ## Why the frame is not 16:9 any more
 *
 * The canvas used to be `sm:aspect-video` over `overflow-hidden`, so its height was a
 * function of its width and anything taller was cut without a trace. Measured on the boxing
 * deck in the media modal (canvas 561 px wide, so 315 px tall): **eight of its nine slides
 * overflowed**, the worst by 908 px — the learner saw 315 px of a 1223 px slide and nothing
 * said so. A projected deck can afford a fixed ratio because the author checks every slide
 * on the same screen; a generated deck read in a modal, in the library and on a phone cannot.
 *
 * So the ratio is a *preference*, not a cage: the frame keeps a width-independent minimum
 * height (`min-h-80`) so a one-line cover still reads as a slide, and grows from there with
 * its content. `overflow-hidden` stays, but now it only rounds the corners — with the height
 * free, there is nothing left for it to clip.
 *
 * ## Why container queries and not `sm:`
 *
 * The deck is always inside something narrower than the window (a `max-w-2xl` modal, a
 * library panel), so viewport breakpoints made the *same* 561 px box lay out differently
 * depending on the window around it — literally "it deforms depending on the view you look
 * at it in". The canvas declares `@container` and every breakpoint below it is a container
 * query, so a slide's layout is decided by the slide's own width and nowhere else.
 */
export function SlideCanvas({ slide, imageUrl }: SlideCanvasProps) {
  const composition = inferComposition(slide)
  const canvasClass =
    'slide-canvas @container flex min-h-80 flex-col overflow-hidden rounded-lg border border-border bg-bg'

  if (composition === 'cover') {
    return (
      <article
        data-slide-composition={composition}
        className={canvasClass}
        aria-label={slide.title}
      >
        {/* The frame itself is the query container, and a container cannot query itself —
            so the composition's own grid lives one level in. */}
        <div className={`flex-1 ${imageUrl ? 'grid @2xl:grid-cols-5' : 'flex'}`}>
          <div className={`flex min-w-0 flex-col justify-center p-7 @lg:p-10 ${imageUrl ? '@2xl:col-span-3' : 'flex-1'}`}>
            <h4 className="max-w-2xl text-2xl font-semibold leading-tight text-text">
              {slide.title}
            </h4>
            {slide.subtitle && (
              <p className="mt-4 max-w-xl text-base leading-relaxed text-text-secondary">
                {slide.subtitle}
              </p>
            )}
          </div>
          {imageUrl && (
            <div className="min-h-48 border-t border-border @2xl:col-span-2 @2xl:border-l @2xl:border-t-0">
              <Illustration src={imageUrl} />
            </div>
          )}
        </div>
      </article>
    )
  }

  const header = (
    <header className="border-b border-border px-6 py-5 @lg:px-8">
      <h4 className="text-xl font-semibold leading-tight text-text">{slide.title}</h4>
      {slide.subtitle && (
        <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{slide.subtitle}</p>
      )}
    </header>
  )

  if (composition === 'statement') {
    return (
      <article
        data-slide-composition={composition}
        className={canvasClass}
        aria-label={slide.title}
      >
        {header}
        <div className={`grid flex-1 ${imageUrl ? '@2xl:grid-cols-5' : ''}`}>
          <div
            className={`flex min-w-0 items-center px-6 py-8 @lg:px-8 ${imageUrl ? '@2xl:col-span-3' : ''}`}
          >
            <Blocks blocks={slide.blocks} />
          </div>
          {imageUrl && (
            <div className="border-t border-border @2xl:col-span-2 @2xl:border-l @2xl:border-t-0">
              <Illustration src={imageUrl} />
            </div>
          )}
        </div>
      </article>
    )
  }

  const supportsSideImage =
    imageUrl != null && ['split', 'process', 'timeline'].includes(composition)

  return (
    <article
      data-slide-composition={composition}
      className={canvasClass}
      aria-label={slide.title}
    >
      {header}
      <div className={supportsSideImage ? 'grid flex-1 @2xl:grid-cols-5' : 'flex-1'}>
        <div className={`min-w-0 p-6 @lg:p-8 ${supportsSideImage ? '@2xl:col-span-3' : ''}`}>
          <Blocks
            blocks={slide.blocks}
            columns={
              composition === 'comparison' ||
              composition === 'grid' ||
              (composition === 'split' && !imageUrl)
            }
          />
        </div>
        {supportsSideImage && (
          <div className="border-t border-border @2xl:col-span-2 @2xl:border-l @2xl:border-t-0">
            <Illustration src={imageUrl} />
          </div>
        )}
      </div>
    </article>
  )
}
