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
        className="h-full w-full object-contain p-8 grayscale contrast-125 sm:p-10"
      />
    </div>
  )
}

function Blocks({ blocks, columns = false }: { blocks: SlideBlockSpec[]; columns?: boolean }) {
  return (
    <div className={columns ? 'grid min-w-0 gap-4 sm:grid-cols-2' : 'min-w-0 space-y-4'}>
      {blocks.map((block, index) => (
        <div key={index} className="min-w-0">
          <SlideBlock block={block} />
        </div>
      ))}
    </div>
  )
}

/**
 * Fixed-format slide renderer: the model chooses a semantic composition, while SkillNet
 * owns every pixel of typography, spacing and data rendering inside a consistent 16:9 frame.
 * Generated imagery is always a supporting ingredient and never replaces the structured slide.
 */
export function SlideCanvas({ slide, imageUrl }: SlideCanvasProps) {
  const composition = inferComposition(slide)
  const canvasClass =
    'slide-canvas min-h-[24rem] overflow-hidden rounded-lg border border-border bg-bg sm:aspect-video sm:min-h-0'

  if (composition === 'cover') {
    return (
      <article
        data-slide-composition={composition}
        className={`${canvasClass} ${imageUrl ? 'grid sm:grid-cols-5' : 'flex'}`}
        aria-label={slide.title}
      >
        <div className={`flex min-w-0 flex-col justify-center p-7 sm:p-10 ${imageUrl ? 'sm:col-span-3' : 'flex-1'}`}>
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
          <div className="min-h-48 border-t border-border sm:col-span-2 sm:border-l sm:border-t-0">
            <Illustration src={imageUrl} />
          </div>
        )}
      </article>
    )
  }

  const header = (
    <header className="border-b border-border px-6 py-5 sm:px-8">
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
        className={`${canvasClass} flex flex-col`}
        aria-label={slide.title}
      >
        {header}
        <div className={`grid min-h-0 flex-1 ${imageUrl ? 'sm:grid-cols-5' : ''}`}>
          <div
            className={`flex min-w-0 items-center px-6 py-8 sm:px-8 ${imageUrl ? 'sm:col-span-3' : ''}`}
          >
            <Blocks blocks={slide.blocks} />
          </div>
          {imageUrl && (
            <div className="border-t border-border sm:col-span-2 sm:border-l sm:border-t-0">
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
      className={`${canvasClass} flex flex-col`}
      aria-label={slide.title}
    >
      {header}
      <div
        className={
          supportsSideImage ? 'grid min-h-0 flex-1 sm:grid-cols-5' : 'min-h-0 flex-1'
        }
      >
        <div className={`min-w-0 p-6 sm:p-8 ${supportsSideImage ? 'sm:col-span-3' : ''}`}>
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
          <div className="border-t border-border sm:col-span-2 sm:border-l sm:border-t-0">
            <Illustration src={imageUrl} />
          </div>
        )}
      </div>
    </article>
  )
}
