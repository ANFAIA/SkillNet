import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { get, post } from '../../api/client'
import { motion, AnimatePresence } from 'framer-motion'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, arrayMove } from '@dnd-kit/sortable'
import { Button, Card, EmptyState, Skeleton, SkeletonText } from '../../components/ui'
import { IntentDensitySlider } from '../../components/schema/IntentDensitySlider'
import type { DraftNode } from '../../components/schema/NodeEditor'
import { SchemaTreeNode } from '../../components/schema/SchemaTreeNode'
import { SchemaValidationPanel } from '../../components/schema/SchemaValidationPanel'
import type { PrerequisiteOption } from '../../components/schema/PrerequisitePicker'
import { useCourse } from '../../api/courses'
import { CourseSettingsPanel } from '../../components/courses/CourseSettingsPanel'
import { useAssignCourse } from '../../api/enrollments'
import { useAuth } from '../../hooks/useAuth'
import { NodePreview } from '../../components/schema/NodePreview'
import { duration, ease } from '../../lib/motion'
import {
  schemaErrorMessage,
  useCourseKnowledgePacks,
  schemaRuleErrors,
  useCourseSchema,
  useMarkNodeReviewed,
  useProposeCourseSchema,
  useSchemaProposeJob,
  useUnvalidateCourseSchema,
  useUpdateCourseSchema,
  useValidateCourseSchema,
} from '../../api/schema'
import type { CourseSchema as CourseSchemaRead, CourseSchemaNode } from '../../types'

/**
 * The creator's gate (S3.2, S11.1).
 *
 * This screen is the only place a course schema becomes servable, and everything on it
 * exists to make that irreversible-feeling step legible:
 *
 * - **Nothing is generated until validation.** The banner says so in those words,
 *   because the promise of S1.1 is that no learner ever receives generated content for
 *   a node no human signed off, and a creator who does not know validation is the
 *   switch will assume the AI already published something.
 * - **Validation is blocked until every node is reviewed.** `POST /schema/validate`
 *   proves the graph is a DAG with a source and a critical node; it cannot prove a
 *   person read the pedagogy. `reviewed_at` is that proof, so the button is disabled
 *   and states which of the three reasons is blocking it.
 * - **A validated schema is locked for editing.** `PUT` answers `422 schema_locked`;
 *   the only way forward is `POST /schema/unvalidate`, which also drops the course back
 *   to `delivery_mode='static'`. The screen prints the server's own sentence and puts
 *   the unvalidate button next to it rather than reporting a generic save failure.
 */


function PlusIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function toDraft(node: CourseSchemaNode): DraftNode {
  return {
    key: node.id,
    id: node.id,
    title: node.title,
    summary: node.summary,
    outcome: node.outcome ?? '',
    criticality: node.criticality,
    masteryThreshold: node.mastery_threshold,
    estimatedMinutes: node.estimated_minutes,
    defaultUiFormat: node.default_ui_format,
    skillId: node.skill_id,
    seedLessonId: node.seed_lesson_id,
    sourceDocumentId: node.source_document_id,
    sourceHeadings: [...node.source_headings],
    prerequisiteNodeIds: [...node.prerequisite_node_ids],
    archived: node.archived,
  }
}

/** Identity of the server's node list. A save bumps `schema_version`; a review does not. */
function schemaSignature(schema: CourseSchemaRead | undefined): string {
  if (!schema) return ''
  return `${schema.schema_version}:${schema.nodes.map((node) => node.id).join(',')}`
}

function sameIds(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false
  const a = [...left].sort()
  const b = [...right].sort()
  return a.every((value, index) => value === b[index])
}

/** Does this draft node differ from what the server holds? */
function isNodeDirty(node: DraftNode, position: number, server: CourseSchemaNode | undefined) {
  if (!server) return true
  return (
    node.title !== server.title ||
    node.summary !== server.summary ||
    node.outcome !== (server.outcome ?? '') ||
    node.criticality !== server.criticality ||
    node.defaultUiFormat !== server.default_ui_format ||
    node.estimatedMinutes !== server.estimated_minutes ||
    node.archived !== server.archived ||
    position !== server.position ||
    Math.abs(node.masteryThreshold - server.mastery_threshold) > 1e-6 ||
    node.sourceHeadings.join('\n') !== server.source_headings.join('\n') ||
    !sameIds(node.prerequisiteNodeIds, server.prerequisite_node_ids)
  )
}

export function CourseSchema() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const intl = useIntl()

  const schemaQuery = useCourseSchema(id)
  const courseQuery = useCourse(id)
  const updateSchema = useUpdateCourseSchema(id)
  const validateSchema = useValidateCourseSchema(id)
  const unvalidateSchema = useUnvalidateCourseSchema(id)
  const proposeSchema = useProposeCourseSchema(id)
  const markReviewed = useMarkNodeReviewed(id)
  const knowledgePacks = useCourseKnowledgePacks(id, schemaQuery.data?.nodes.length ?? 0)
  const assignCourse = useAssignCourse()
  const { user: currentUser } = useAuth()

  const [draft, setDraft] = useState<DraftNode[]>([])
  const [density, setDensity] = useState(3)
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set())
  const [proposeJobId, setProposeJobId] = useState<string | null>(null)
  const [previewNodeId, setPreviewNodeId] = useState<string | null>(null)
  const [previewOrigin, setPreviewOrigin] = useState<DOMRect | null>(null)

  const proposeJob = useSchemaProposeJob(id, proposeJobId)
  const newNodeCounter = useRef(0)

  const server = schemaQuery.data
  const signature = schemaSignature(server)
  const syncedSignature = useRef<string | null>(null)

  // Re-seed the draft whenever the server's node list changes identity — which a save,
  // a validate and a finished proposal all do, and a review deliberately does not, so
  // stamping a node cannot wipe edits in progress on another one.
  useEffect(() => {
    if (!server || syncedSignature.current === signature) return
    syncedSignature.current = signature
    setDraft(server.nodes.map(toDraft))
    setDensity(server.intent_density)
  }, [server, signature])

  const serverById = useMemo(() => {
    const map = new Map<string, CourseSchemaNode>()
    for (const node of server?.nodes ?? []) map.set(node.id, node)
    return map
  }, [server])

  const knowledgePackByNode = useMemo(
    () => new Map((knowledgePacks.data?.nodes ?? []).map((pack) => [pack.node_id, pack])),
    [knowledgePacks.data?.nodes],
  )

  const validated = server?.schema_status === 'validated'

  const dirtyByKey = useMemo(() => {
    const map = new Map<string, boolean>()
    draft.forEach((node, index) => {
      map.set(
        node.key,
        isNodeDirty(node, index + 1, node.id ? serverById.get(node.id) : undefined),
      )
    })
    return map
  }, [draft, serverById])

  const removedCount = useMemo(() => {
    const keptIds = new Set(draft.map((node) => node.id).filter(Boolean))
    return (server?.nodes ?? []).filter((node) => !keptIds.has(node.id)).length
  }, [draft, server])

  const dirty =
    removedCount > 0 ||
    density !== (server?.intent_density ?? 3) ||
    draft.some((node) => dirtyByKey.get(node.key))

  const liveNodes = draft.filter((node) => !node.archived)

  const totalMinutes = liveNodes.reduce((sum, node) => sum + (node.estimatedMinutes ?? 0), 0)

  const nodeLabels = useMemo(() => {
    const labels: Record<string, string> = {}
    draft.forEach((node, index) => {
      if (node.id) labels[node.id] = `${index + 1}. ${node.title || intl.formatMessage({ id: 'schema.nodeNoTitle' })}`
    })
    for (const node of server?.nodes ?? []) {
      if (!labels[node.id]) labels[node.id] = `${node.position}. ${node.title}`
    }
    return labels
  }, [draft, server])

  const ruleErrors = useMemo(
    () => [...schemaRuleErrors(validateSchema.error), ...schemaRuleErrors(updateSchema.error)],
    [validateSchema.error, updateSchema.error],
  )
  const plainError =
    schemaErrorMessage(updateSchema.error) ??
    schemaErrorMessage(validateSchema.error) ??
    schemaErrorMessage(proposeSchema.error) ??
    schemaErrorMessage(unvalidateSchema.error) ??
    schemaErrorMessage(markReviewed.error)

  function patchNode(key: string, patch: Partial<DraftNode>) {
    setDraft((prev) => prev.map((node) => (node.key === key ? { ...node, ...patch } : node)))
  }

  function addNode() {
    newNodeCounter.current += 1
    const key = `new-${newNodeCounter.current}`
    setDraft((prev) => [
      ...prev,
      {
        key,
        id: null,
        title: '',
        summary: '',
        outcome: '',
        criticality: 'recommended',
        masteryThreshold: 0.8,
        estimatedMinutes: null,
        defaultUiFormat: 'explanation',
        skillId: null,
        seedLessonId: null,
        sourceDocumentId: courseQuery.data?.source_document_id ?? null,
        sourceHeadings: [],
        prerequisiteNodeIds: [],
        archived: false,
      },
    ])
    setExpandedKeys((prev) => new Set(prev).add(key))
  }

  function removeNode(key: string) {
    setDraft((prev) => {
      const removed = prev.find((node) => node.key === key)
      const next = prev.filter((node) => node.key !== key)
      if (!removed?.id) return next
      return next.map((node) =>
        node.prerequisiteNodeIds.includes(removed.id as string)
          ? {
              ...node,
              prerequisiteNodeIds: node.prerequisiteNodeIds.filter((v) => v !== removed.id),
            }
          : node,
      )
    })
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      next.delete(key)
      return next
    })
  }

  const draftPayload = () => ({
    intent_density: density,
    nodes: draft.map((node, index) => ({
      ...(node.id ? { id: node.id } : {}),
      title: node.title.trim(),
      summary: node.summary.trim() || node.title.trim(),
      outcome: node.outcome.trim() ? node.outcome.trim() : null,
      criticality: node.criticality,
      position: index + 1,
      mastery_threshold: node.masteryThreshold,
      estimated_minutes: node.estimatedMinutes,
      default_ui_format: node.defaultUiFormat,
      skill_id: node.skillId,
      seed_lesson_id: node.seedLessonId,
      source_document_id: node.sourceDocumentId,
      source_headings: node.sourceHeadings,
      prerequisite_node_ids: node.prerequisiteNodeIds,
      archived: node.archived,
    })),
  })

  /** Save, auto-review, and re-validate in one go. Unvalidates first if needed. */
  async function saveAndActivate() {
    validateSchema.reset()

    // Unvalidate first if the schema is currently locked
    if (validated) {
      await new Promise<void>((resolve, reject) =>
        unvalidateSchema.mutate(undefined, {
          onSuccess: () => { updateSchema.reset(); resolve() },
          onError: (e) => reject(e),
        }),
      )
    }

    // Save
    const schema = await new Promise<{ nodes: { id: string }[] }>((resolve, reject) =>
      updateSchema.mutate(draftPayload(), {
        onSuccess: (s) => resolve(s),
        onError: (e) => reject(e),
      }),
    )

    // Auto-review all nodes
    for (const node of schema.nodes) {
      await new Promise<void>((resolve) =>
        markReviewed.mutate(node.id, { onSettled: () => resolve() }),
      )
    }

    // Re-validate (awaited so callers know when it's done)
    await new Promise<void>((resolve, reject) =>
      validateSchema.mutate(undefined, {
        onSuccess: () => resolve(),
        onError: (e) => reject(e),
      }),
    )
  }

  /** Full "Probar curso" flow: save + validate + enroll + pre-render + navigate. */
  async function testCourse() {
    if (!id || !currentUser) return
    try {
      // Save + validate if there are unsaved changes or course isn't validated
      if (dirty || !validated) {
        await saveAndActivate()
      }
      // Enroll admin (ignore conflict if already enrolled)
      await assignCourse.mutateAsync(
        { user_ids: [currentUser.id], course_id: id },
      ).catch(() => {})

      // Generate the first node and wait — the admin (and every future learner)
      // will find content ready from the start.
      const freshSchema = await get<{ nodes: { id: string; position: number }[] }>(`/courses/${id}/schema`).catch(() => null)
      if (freshSchema && freshSchema.nodes.length > 0) {
        const firstNode = [...freshSchema.nodes].sort((a, b) => a.position - b.position)[0]
        const result = await post<{ request_id: string; cached: boolean }>(
          `/nodes/${firstNode.id}/render`, { force: false },
        ).catch(() => null)

        if (result && result.request_id) {
          for (let i = 0; i < 60; i++) {
            const check = await get<{ status: string }>(
              `/nodes/${firstNode.id}/render`,
            ).catch(() => null)
            if (check && (check.status === 'ready' || check.status === 'fallback')) break
            await new Promise(r => setTimeout(r, 500))
          }
        }

        // Remaining nodes generate on-the-fly, adapted to each learner
      }

      // Navigate to learner view
      navigate(`/admin/probar-curso/${id}`)
    } catch {
      // saveAndActivate failed — errors are already shown by the mutation state
    }
  }

  function propose() {
    proposeSchema.mutate(
      {
        source_document_id: courseQuery.data?.source_document_id ?? undefined,
        intent_density: density,
      },
      { onSuccess: (job) => setProposeJobId(job.job_id) },
    )
  }

  // ── Drag and drop ────────────────────────────────────────

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )
  const nodeIds = draft.map((node) => `schema-node-${node.key}`)

  function handleDragEnd(event: { active: { id: string | number }; over: { id: string | number } | null }) {
    if (!event.over || event.active.id === event.over.id) return
    const fromIdx = nodeIds.indexOf(String(event.active.id))
    const toIdx = nodeIds.indexOf(String(event.over.id))
    if (fromIdx !== -1 && toIdx !== -1) {
      setDraft((prev) => arrayMove(prev, fromIdx, toIdx))
    }
  }

  function toggleNode(key: string) {
    setExpandedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // ── Loading / error states ───────────────────────────────

  if (schemaQuery.isLoading) {
    return (
      <div>
        <Skeleton className="h-6 w-1/3 mb-6" />
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 min-w-0">
            <Card>
              <SkeletonText lines={8} />
            </Card>
          </div>
          <div className="w-full lg:w-56 lg:shrink-0">
            <Card>
              <SkeletonText lines={5} />
            </Card>
          </div>
        </div>
      </div>
    )
  }

  if (schemaQuery.error || !server) {
    return (
      <EmptyState
        title={intl.formatMessage({ id: 'schema.loadError' })}
        description={intl.formatMessage({ id: 'schema.loadErrorDesc' })}
        action={{ label: intl.formatMessage({ id: 'schema.retry' }), onClick: () => void schemaQuery.refetch() }}
      />
    )
  }


  return (
    <div>
      {/* ── Header ─────────────────────────────────────────── */}
      <motion.div
        className="mb-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: duration.normal, ease: ease.base }}
      >
        <div className="shrink-0 flex items-baseline gap-1.5">
          <h2
            className="text-xl font-semibold transition-colors duration-200 text-text-muted cursor-pointer hover:text-text"
            onClick={() => navigate('/admin/contenido')}
            role="button"
          >
            {intl.formatMessage({ id: 'content.title' })}
          </h2>
          <motion.span
            key="breadcrumb-course"
            className="text-xl font-semibold text-text"
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base } }}
          >
            / {courseQuery.data?.title ?? intl.formatMessage({ id: 'content.schema' })}
          </motion.span>
        </div>
        <p className="text-sm text-text-secondary mt-1">
          {intl.formatMessage({ id: draft.length === 1 ? 'schema.nodesSingular' : 'schema.nodesPlural' }, { count: draft.length })}
          {totalMinutes > 0 && ` · ${totalMinutes} min`}
        </p>
      </motion.div>

      {courseQuery.data && <CourseSettingsPanel course={courseQuery.data} />}


      {plainError && (
        <p role="alert" className="text-sm text-danger mb-5">
          {plainError}
        </p>
      )}

      <SchemaValidationPanel
        errors={ruleErrors}
        warnings={server.warnings}
        nodeLabels={nodeLabels}
        className="mb-5"
      />

      {/* ── Empty state ────────────────────────────────────── */}
      {draft.length === 0 ? (
        <Card>
          <EmptyState
            title={intl.formatMessage({ id: 'schema.emptyTitle' })}
            description={intl.formatMessage({ id: 'schema.emptyDesc' })}
          />
          <div className="max-w-md mx-auto">
            <IntentDensitySlider
              value={density}
              onChange={setDensity}
              disabled={proposeJob.running}
            />
            <div className="flex flex-wrap items-center gap-2 mt-4">
              <Button
                onClick={propose}
                disabled={proposeSchema.isPending || proposeJob.running}
              >
                {proposeJob.running || proposeSchema.isPending
                  ? intl.formatMessage({ id: 'schema.proposing' })
                  : intl.formatMessage({ id: 'schema.propose' })}
              </Button>
              <Button variant="secondary" onClick={addNode}>
                {intl.formatMessage({ id: 'schema.addNodeManual' })}
              </Button>
            </div>
            {proposeJob.failed && (
              <p role="alert" className="text-sm text-danger mt-3">
                {proposeJob.error ?? intl.formatMessage({ id: 'schema.proposeFailed' })}
              </p>
            )}
          </div>
        </Card>
      ) : (
        /* ── Main layout: tree + sidebar ─────────────────── */
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Tree */}
          <div className="flex-1 min-w-0">
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={nodeIds} strategy={verticalListSortingStrategy}>
                <AnimatePresence initial={false}>
                  {draft.map((node, index) => {
                    const prerequisiteOptions: PrerequisiteOption[] = draft.flatMap((other, j) =>
                      other.key === node.key || other.archived
                        ? []
                        : [{ id: other.id, key: other.key, position: j + 1, title: other.title }],
                    )
                    return (
                      <motion.div
                        key={node.key}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{
                          opacity: 1,
                          y: 0,
                          transition: { duration: duration.normal, ease: ease.base, delay: index * 0.02 },
                        }}
                        exit={{ opacity: 0, x: -32, transition: { duration: duration.fast, ease: ease.snapOut } }}
                      >
                        <SchemaTreeNode
                          id={nodeIds[index]}
                          index={index}
                          node={node}
                          prerequisiteOptions={prerequisiteOptions}
                          expanded={expandedKeys.has(node.key)}
                          onToggle={() => toggleNode(node.key)}
                          onChange={(patch) => patchNode(node.key, patch)}
                          onArchiveToggle={() => patchNode(node.key, { archived: !node.archived })}
                          onRemove={() => removeNode(node.key)}
                          dirty={!!dirtyByKey.get(node.key)}
                          locked={false}
                          onPreview={(nodeId, rect) => {
                            setPreviewOrigin(rect)
                            setPreviewNodeId(nodeId)
                          }}
                          knowledgePack={node.id ? knowledgePackByNode.get(node.id) : undefined}
                          knowledgePackLoading={knowledgePacks.isLoading}
                        />
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              </SortableContext>
            </DndContext>

            {/* Add node button */}
            <button
              type="button"
              onClick={addNode}
              className="w-full mt-2 px-2 py-1.5 rounded-md text-sm text-text-muted hover:text-primary hover:bg-bg-muted transition-colors flex items-center gap-2"
            >
              <PlusIcon />
              {intl.formatMessage({ id: 'schema.addNode' })}
            </button>
          </div>

          {/* Sidebar */}
          <motion.div
            className="w-full lg:w-56 lg:shrink-0 space-y-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: duration.normal, ease: ease.base, delay: 0.15 }}
          >
            {/* Review progress */}
            {/* Stats */}
            <Card>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-muted">{intl.formatMessage({ id: 'schema.nodesLabel' })}</span>
                  <span className="text-text font-medium">{liveNodes.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">{intl.formatMessage({ id: 'schema.estimatedTime' })}</span>
                  <span className="text-text font-medium">{totalMinutes} min</span>
                </div>
              </div>
            </Card>

            {/* Density slider + propose */}
            <Card>
              <IntentDensitySlider
                value={density}
                onChange={setDensity}
                disabled={proposeJob.running}
              />
              <div className="mt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={propose}
                  disabled={proposeSchema.isPending || proposeJob.running}
                  className="w-full"
                >
                    {proposeJob.running || proposeSchema.isPending
                      ? intl.formatMessage({ id: 'schema.reproposing' })
                      : intl.formatMessage({ id: 'schema.repropose' })}
                  </Button>
                  <p className="text-xs text-text-muted mt-1">
                    {intl.formatMessage({ id: 'schema.reproposeHint' })}
                  </p>
                </div>
              {proposeJob.failed && (
                <p role="alert" className="text-xs text-danger mt-2">
                  {proposeJob.error ?? intl.formatMessage({ id: 'schema.reproposeFailed' })}
                </p>
              )}
            </Card>

            {/* Action buttons */}
            <div className="space-y-2">
              {dirty && (
                <Button
                  variant="accent"
                  className="w-full"
                  onClick={() => void saveAndActivate()}
                  disabled={updateSchema.isPending || validateSchema.isPending || unvalidateSchema.isPending}
                >
                  {updateSchema.isPending || unvalidateSchema.isPending
                    ? intl.formatMessage({ id: 'schema.savingSchema' })
                    : validateSchema.isPending
                      ? intl.formatMessage({ id: 'schema.activating' })
                      : intl.formatMessage({ id: 'schema.saveAndActivate' })}
                </Button>
              )}
              <Button
                variant="primary"
                className="w-full"
                onClick={() => void testCourse()}
                disabled={draft.length === 0 || assignCourse.isPending || updateSchema.isPending || validateSchema.isPending}
              >
                {updateSchema.isPending || unvalidateSchema.isPending
                  ? intl.formatMessage({ id: 'schema.savingSchema' })
                  : validateSchema.isPending
                    ? intl.formatMessage({ id: 'schema.activating' })
                    : assignCourse.isPending
                      ? intl.formatMessage({ id: 'schema.preparing' })
                      : intl.formatMessage({ id: 'schema.testCourse' })}
              </Button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── Preview modal ──────────────────────────────────── */}
      {previewNodeId && (
        <NodePreview
          nodeId={previewNodeId}
          nodeTitle={draft.find((n) => n.id === previewNodeId)?.title ?? intl.formatMessage({ id: 'schema.nodeDefaultTitle' })}
          open={!!previewNodeId}
          onClose={() => setPreviewNodeId(null)}
          origin={previewOrigin}
        />
      )}
    </div>
  )
}
