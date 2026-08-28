import { motion } from 'framer-motion'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useIntl } from 'react-intl'
import { duration } from '../../lib/motion'
import { InfoTooltip } from '../ui/InfoTooltip'
import { Button } from '../ui'
import { DEFAULT_MASTERY_THRESHOLD } from './CriticalityBadge'
import { PrerequisitePicker, type PrerequisiteOption } from './PrerequisitePicker'
import type { DraftNode } from './NodeEditor'
import { NodeKnowledgePreparation } from './NodeKnowledgePreparation'
import type { NodeKnowledgePack } from '../../types'

// ── Icons ──────────────────────────────────────────────────

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}



// ── Component ──────────────────────────────────────────────

export interface SchemaTreeNodeProps {
  id: string
  index: number
  node: DraftNode
  prerequisiteOptions: PrerequisiteOption[]
  expanded: boolean
  onToggle: () => void
  onChange: (patch: Partial<DraftNode>) => void
  onArchiveToggle: () => void
  onRemove: () => void
  /** Local edits not yet saved. */
  dirty: boolean
  /** Schema is validated — all editing disabled. */
  locked: boolean
  /** Callback to preview the node content. */
  onPreview: (nodeId: string, rect: DOMRect) => void
  knowledgePack?: NodeKnowledgePack
  knowledgePackLoading: boolean
}

export function SchemaTreeNode({
  id,
  index,
  node,
  prerequisiteOptions,
  expanded,
  onToggle,
  onChange,
  onArchiveToggle,
  onRemove,
  dirty,
  locked,
  onPreview,
  knowledgePack,
  knowledgePackLoading,
}: SchemaTreeNodeProps) {
  const intl = useIntl()
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition: dndTransition,
    isDragging,
  } = useSortable({ id, disabled: locked })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition: dndTransition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const disabled = locked

  const thresholdIsDefault =
    Math.abs(node.masteryThreshold - DEFAULT_MASTERY_THRESHOLD[node.criticality]) < 0.001

  return (
    <div ref={setNodeRef} style={style}>
      {/* Row: always visible */}
      <div
        className={`flex items-start gap-0 px-2 py-1.5 rounded-md group transition-colors ${
          expanded ? 'bg-bg-subtle' : 'hover:bg-bg-muted'
        }`}
      >
        {/* Drag handle */}
        {!locked && (
          <button
            {...attributes}
            {...listeners}
            className="w-5 shrink-0 flex flex-col items-center gap-0.5 cursor-grab text-text-muted opacity-0 group-hover:opacity-100 transition-opacity mt-0.5"
            title={intl.formatMessage({ id: 'schemaNode.drag' })}
          >
            <span className="block w-2.5 h-0.5 bg-current rounded-full" />
            <span className="block w-2.5 h-0.5 bg-current rounded-full" />
            <span className="block w-2.5 h-0.5 bg-current rounded-full" />
          </button>
        )}
        {locked && <span className="w-5 shrink-0" />}

        {/* Toggle */}
        <button
          type="button"
          onClick={onToggle}
          aria-label={intl.formatMessage(
            { id: expanded ? 'schemaNode.collapse' : 'schemaNode.expand' },
            { title: node.title },
          )}
          className="text-text-muted hover:text-text shrink-0 mt-0.5"
        >
          <ChevronIcon open={expanded} />
        </button>

        {/* Node number */}
        <span className="text-xs font-medium text-text-muted w-5 flex items-center justify-center shrink-0 ml-1 mt-0.5">
          {index + 1}
        </span>

        {/* Title + summary (collapsed) */}
        <div className="flex-1 min-w-0 ml-2">
          {locked ? (
            <span className="text-sm font-medium text-text">{node.title || intl.formatMessage({ id: 'schema.nodeNoTitle' })}</span>
          ) : (
            <input
              className="w-full text-sm font-medium text-text bg-transparent border-none focus:outline-none focus:ring-0 p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1 focus:-mx-1"
              value={node.title}
              onChange={(e) => onChange({ title: e.target.value })}
              placeholder={intl.formatMessage({ id: 'schemaNode.titlePlaceholder' })}
              disabled={disabled}
            />
          )}
          {!expanded && node.summary && (
            <p className="text-xs text-text-muted truncate mt-0.5">{node.summary}</p>
          )}
        </div>

        {/* Meta indicators */}
        <div className="flex items-center gap-2 shrink-0 ml-2 mt-0.5">
          {/* Dirty indicator */}
          {dirty && (
            <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" title={intl.formatMessage({ id: 'schemaNode.unsavedChanges' })} />
          )}

          {!expanded && node.archived && (
            <span className="text-xs text-text-muted">Arch.</span>
          )}
        </div>
      </div>

      {/* Expanded form */}
      {expanded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.fast } }}
          className="ml-[42px] pl-4 border-l border-border space-y-1 pb-3"
        >
          {/* Summary */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">{intl.formatMessage({ id: 'schemaNode.summary' })}</span>
            <textarea
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 resize-none leading-relaxed focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:py-0.5 focus:-mx-1.5 focus:-my-0.5 disabled:opacity-50"
              value={node.summary}
              onChange={(e) => onChange({ summary: e.target.value })}
              rows={1}
              disabled={disabled}
              onInput={(e) => {
                const t = e.target as HTMLTextAreaElement
                t.style.height = 'auto'
                t.style.height = t.scrollHeight + 'px'
              }}
            />
          </div>

          {/* Outcome */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">{intl.formatMessage({ id: 'schemaNode.outcome' })}</span>
            <input
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5 disabled:opacity-50"
              value={node.outcome}
              onChange={(e) => onChange({ outcome: e.target.value })}
              placeholder={intl.formatMessage({ id: 'schemaNode.outcomePlaceholder' })}
              disabled={disabled}
            />
          </div>

          {/* Mastery threshold */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted flex items-center">
              {intl.formatMessage({ id: 'schemaNode.threshold' })}
              <InfoTooltip text={intl.formatMessage({ id: 'schemaNode.thresholdTooltip' })} />
            </span>
            <input
              type="number"
              min={50}
              max={100}
              step={5}
              className="w-16 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5 disabled:opacity-50"
              value={Math.round(node.masteryThreshold * 100)}
              disabled={disabled}
              onChange={(e) => {
                const parsed = Number(e.target.value)
                if (Number.isNaN(parsed)) return
                onChange({ masteryThreshold: parsed / 100 })
              }}
            />
            <span className="text-xs text-text-muted ml-1">%</span>
            <span className="text-xs text-text-muted ml-2">
              {thresholdIsDefault
                ? intl.formatMessage({ id: 'schemaNode.thresholdDefault' })
                : intl.formatMessage({ id: 'schemaNode.thresholdCustom' })}
            </span>
          </div>

          {/* Prerequisites */}
          <div className="px-2 py-1">
            <PrerequisitePicker
              options={prerequisiteOptions}
              selected={node.prerequisiteNodeIds}
              onChange={(next) => onChange({ prerequisiteNodeIds: next })}
              disabled={disabled}
            />
          </div>

          <NodeKnowledgePreparation
            pack={knowledgePack}
            loading={knowledgePackLoading}
          />

          {/* Action row */}
          <div className="flex flex-wrap items-center gap-2 px-2 pt-2 border-t border-border mt-2">
            {/* Preview */}
            {node.id && !dirty && (
              <Button
                variant="secondary"
                size="sm"
                onClick={(e) => {
                  onPreview(node.id!, e.currentTarget.getBoundingClientRect())
                }}
              >
                {intl.formatMessage({ id: 'schemaNode.preview' })}
              </Button>
            )}

            {/* Archive / remove */}
            {!locked && (
              <>
                <Button variant="ghost" size="sm" onClick={onArchiveToggle}>
                  {node.archived
                    ? intl.formatMessage({ id: 'schemaNode.unarchive' })
                    : intl.formatMessage({ id: 'schemaNode.archive' })}
                </Button>
                <Button variant="ghost" size="sm" onClick={onRemove}>
                  {intl.formatMessage({ id: 'schemaNode.remove' })}
                </Button>
              </>
            )}
          </div>

        </motion.div>
      )}
    </div>
  )
}
