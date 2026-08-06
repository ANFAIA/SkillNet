import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
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
import { Button, Card, EmptyState, ProgressBar, Skeleton, SkeletonText } from '../../components/ui'
import { CriticalityBadge } from '../../components/schema/CriticalityBadge'
import { IntentDensitySlider } from '../../components/schema/IntentDensitySlider'
import type { DraftNode } from '../../components/schema/NodeEditor'
import { SchemaTreeNode } from '../../components/schema/SchemaTreeNode'
import { SchemaValidationPanel } from '../../components/schema/SchemaValidationPanel'
import type { PrerequisiteOption } from '../../components/schema/PrerequisitePicker'
import { useCourse } from '../../api/courses'
import { useAssignCourse } from '../../api/enrollments'
import { useAuth } from '../../hooks/useAuth'
import { NodePreview } from '../../components/schema/NodePreview'
import { duration, ease } from '../../lib/motion'
import {
  schemaErrorMessage,
  schemaLockedMessage,
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

const STATUS_COPY: Record<string, { label: string; className: string }> = {
  draft: { label: 'Borrador', className: 'bg-bg-muted text-text-secondary' },
  proposed: { label: 'Propuesto', className: 'bg-primary-subtle text-primary' },
  validated: { label: 'Validado', className: 'bg-accent-subtle text-accent' },
  archived: { label: 'Archivado', className: 'bg-bg-muted text-text-secondary' },
}

function StatusPill({ status }: { status: string }) {
  const copy = STATUS_COPY[status] ?? {
    label: status,
    className: 'bg-bg-muted text-text-secondary',
  }
  return (
    <span
      className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${copy.className}`}
    >
      {copy.label}
    </span>
  )
}

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

  const schemaQuery = useCourseSchema(id)
  const courseQuery = useCourse(id)
  const updateSchema = useUpdateCourseSchema(id)
  const validateSchema = useValidateCourseSchema(id)
  const unvalidateSchema = useUnvalidateCourseSchema(id)
  const proposeSchema = useProposeCourseSchema(id)
  const markReviewed = useMarkNodeReviewed(id)
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

  const locked = server?.schema_status === 'validated'

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
  const criticalCount = liveNodes.filter((node) => node.criticality === 'critical').length
  const reviewedCount = liveNodes.filter((node) => {
    const stamped = node.id ? serverById.get(node.id)?.reviewed_at : null
    return stamped && !dirtyByKey.get(node.key)
  }).length
  const unreviewedCount = liveNodes.length - reviewedCount

  const totalMinutes = liveNodes.reduce((sum, node) => sum + (node.estimatedMinutes ?? 0), 0)

  const nodeLabels = useMemo(() => {
    const labels: Record<string, string> = {}
    draft.forEach((node, index) => {
      if (node.id) labels[node.id] = `${index + 1}. ${node.title || 'Nodo sin titulo'}`
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
  const lockedNotice =
    schemaLockedMessage(updateSchema.error) ?? schemaLockedMessage(proposeSchema.error)
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

  function unvalidate() {
    unvalidateSchema.mutate(undefined, { onSuccess: () => updateSchema.reset() })
  }

  function save() {
    validateSchema.reset()
    updateSchema.mutate({
      intent_density: density,
      nodes: draft.map((node, index) => ({
        ...(node.id ? { id: node.id } : {}),
        title: node.title.trim(),
        summary: node.summary.trim(),
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
        title="No se pudo cargar el esquema"
        description="Vuelve a intentarlo en unos segundos."
        action={{ label: 'Reintentar', onClick: () => void schemaQuery.refetch() }}
      />
    )
  }

  const validateBlockedReason = locked
    ? 'Este esquema ya esta validado.'
    : draft.length === 0
      ? 'El esquema no tiene nodos.'
      : dirty
        ? 'Guarda los cambios antes de validar: se valida lo que hay en el servidor.'
        : unreviewedCount > 0
          ? unreviewedCount === 1
            ? 'Queda 1 nodo sin revisar.'
            : `Quedan ${unreviewedCount} nodos sin revisar.`
          : null

  return (
    <div>
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="mb-6">
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => navigate('/admin/contenido')}
            className="group shrink-0 p-1 -ml-1"
            aria-label="Volver a contenido"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-text-muted group-hover:text-primary group-hover:-translate-x-1 transition-all duration-200"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h2 className="text-xl font-semibold text-text truncate min-w-0">
            {courseQuery.data?.title ?? 'Esquema del curso'}
          </h2>
          <StatusPill status={server.schema_status} />
        </div>
        <p className="text-sm text-text-secondary mt-1">
          Esquema v{server.schema_version} · {draft.length}{' '}
          {draft.length === 1 ? 'nodo' : 'nodos'} ·{' '}
          {server.delivery_mode === 'dynamic' ? 'entrega dinamica' : 'entrega estatica'}
        </p>
      </div>

      {/* ── Locked / draft banner ──────────────────────────── */}
      {locked ? (
        <div className="border border-accent/40 bg-accent-subtle rounded-lg p-4 mb-5 min-w-0">
          <p className="text-sm font-medium text-text">Esquema validado y en servicio</p>
          <p className="text-sm text-text-secondary mt-1">
            Los aprendices matriculados reciben lecciones generadas nodo a nodo. Para editar
            el esquema hay que sacarlo de validacion, lo que devuelve el curso al modo
            estatico hasta que lo vuelvas a validar.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            onClick={unvalidate}
            disabled={unvalidateSchema.isPending}
          >
            {unvalidateSchema.isPending ? 'Sacando...' : 'Sacar de validacion'}
          </Button>
        </div>
      ) : (
        <div className="border border-border bg-bg-subtle rounded-lg p-4 mb-5 min-w-0">
          <p className="text-sm font-medium text-text">Todavia no se genera nada</p>
          <p className="text-sm text-text-secondary mt-1">
            Hasta que valides este esquema, ningun aprendiz recibe contenido de este curso y
            no se genera ninguna leccion. Revisa nodo a nodo y valida cuando el esquema te
            convenza.
          </p>
        </div>
      )}

      {/* ── Locked notice from server ──────────────────────── */}
      {lockedNotice && (
        <div role="alert" className="border border-danger/40 bg-danger/5 rounded-lg p-4 mb-5">
          <p className="text-sm font-medium text-danger">No se guardo nada</p>
          <p className="text-sm text-text mt-1">{lockedNotice}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            onClick={unvalidate}
            disabled={unvalidateSchema.isPending}
          >
            {unvalidateSchema.isPending ? 'Sacando...' : 'Sacar de validacion'}
          </Button>
        </div>
      )}

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
            title="Este curso no tiene esquema todavia"
            description="Propon un esquema a partir del documento de origen y luego revisa nodo a nodo, o construyelo a mano."
          />
          <div className="max-w-md mx-auto">
            <IntentDensitySlider
              value={density}
              onChange={setDensity}
              disabled={locked || proposeJob.running}
            />
            <div className="flex flex-wrap items-center gap-2 mt-4">
              <Button
                onClick={propose}
                disabled={locked || proposeSchema.isPending || proposeJob.running}
              >
                {proposeJob.running || proposeSchema.isPending
                  ? 'Proponiendo esquema...'
                  : 'Proponer esquema'}
              </Button>
              <Button variant="secondary" onClick={addNode} disabled={locked}>
                Anadir nodo a mano
              </Button>
            </div>
            {proposeJob.failed && (
              <p role="alert" className="text-sm text-danger mt-3">
                {proposeJob.error ?? 'La propuesta de esquema fallo.'}
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
                          total={draft.length}
                          prerequisiteOptions={prerequisiteOptions}
                          expanded={expandedKeys.has(node.key)}
                          onToggle={() => toggleNode(node.key)}
                          onChange={(patch) => patchNode(node.key, patch)}
                          onArchiveToggle={() => patchNode(node.key, { archived: !node.archived })}
                          onRemove={() => removeNode(node.key)}
                          reviewedAt={node.id ? serverById.get(node.id)?.reviewed_at ?? null : null}
                          dirty={!!dirtyByKey.get(node.key)}
                          locked={!!locked}
                          onMarkReviewed={(nodeId) => markReviewed.mutate(nodeId)}
                          markReviewPending={
                            markReviewed.isPending && markReviewed.variables === node.id
                          }
                          onPreview={(nodeId, rect) => {
                            setPreviewOrigin(rect)
                            setPreviewNodeId(nodeId)
                          }}
                        />
                      </motion.div>
                    )
                  })}
                </AnimatePresence>
              </SortableContext>
            </DndContext>

            {/* Add node button */}
            {!locked && (
              <button
                type="button"
                onClick={addNode}
                className="w-full mt-2 px-2 py-1.5 rounded-md text-sm text-text-muted hover:text-primary hover:bg-bg-muted transition-colors flex items-center gap-2"
              >
                <PlusIcon />
                Anadir nodo
              </button>
            )}
          </div>

          {/* Sidebar */}
          <div className="w-full lg:w-56 lg:shrink-0 space-y-4">
            {/* Review progress */}
            <Card>
              <div className="flex items-baseline justify-between gap-2 mb-2">
                <h3 className="text-sm font-medium text-text">Revision</h3>
                <span className="text-xs text-text-muted shrink-0 tabular-nums">
                  {reviewedCount} de {liveNodes.length}
                </span>
              </div>
              <ProgressBar
                value={liveNodes.length === 0 ? 0 : (reviewedCount / liveNodes.length) * 100}
                size="sm"
              />
              <p className="text-xs text-text-secondary mt-2">
                {unreviewedCount === 0 && liveNodes.length > 0
                  ? 'Todos los nodos estan revisados.'
                  : unreviewedCount === 1
                    ? 'Queda 1 nodo por revisar.'
                    : `Quedan ${unreviewedCount} nodos por revisar.`}
              </p>
            </Card>

            {/* Stats */}
            <Card>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-muted">Nodos</span>
                  <span className="text-text font-medium">{liveNodes.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Imprescindibles</span>
                  <span className="text-text font-medium">{criticalCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-muted">Tiempo est.</span>
                  <span className="text-text font-medium">{totalMinutes} min</span>
                </div>
              </div>
            </Card>

            {/* Density slider + propose */}
            <Card>
              <IntentDensitySlider
                value={density}
                onChange={setDensity}
                disabled={locked || proposeJob.running}
              />
              {!locked && (
                <div className="mt-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={propose}
                    disabled={proposeSchema.isPending || proposeJob.running}
                    className="w-full"
                  >
                    {proposeJob.running || proposeSchema.isPending
                      ? 'Proponiendo...'
                      : 'Volver a proponer'}
                  </Button>
                  <p className="text-xs text-text-muted mt-1">
                    Reemplaza los nodos propuestos por una tanda nueva.
                  </p>
                </div>
              )}
              {proposeJob.failed && (
                <p role="alert" className="text-xs text-danger mt-2">
                  {proposeJob.error ?? 'La propuesta fallo.'}
                </p>
              )}
            </Card>

            {/* Action buttons */}
            <div className="space-y-2">
              <Button
                variant="secondary"
                className="w-full"
                onClick={save}
                disabled={locked || !dirty || updateSchema.isPending}
              >
                {updateSchema.isPending ? 'Guardando...' : 'Guardar cambios'}
              </Button>
              <Button
                variant="accent"
                className="w-full"
                onClick={() => validateSchema.mutate()}
                disabled={!!validateBlockedReason || validateSchema.isPending}
                title={validateBlockedReason ?? 'Activa la entrega dinamica de este curso'}
              >
                {validateSchema.isPending ? 'Validando...' : 'Validar esquema'}
              </Button>
              {locked && id && (
                <Button
                  variant="primary"
                  className="w-full"
                  onClick={() => {
                    if (!id || !currentUser) return
                    assignCourse.mutate(
                      { user_ids: [currentUser.id], course_id: id },
                      {
                        onSuccess: () => navigate(`/empleado/curso/${id}`),
                        onError: () => navigate(`/empleado/curso/${id}`),
                      },
                    )
                  }}
                  disabled={assignCourse.isPending}
                >
                  {assignCourse.isPending ? 'Preparando...' : 'Probar curso'}
                </Button>
              )}
              {validateBlockedReason && !locked && (
                <p className="text-xs text-text-muted">{validateBlockedReason}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Footer: critical count ─────────────────────────── */}
      {draft.length > 0 && (
        <div className="flex items-center gap-2 mt-6 pt-4 border-t border-border min-w-0">
          {criticalCount > 0 && (
            <>
              <CriticalityBadge criticality="critical" />
              <span className="text-xs text-text-muted">
                {criticalCount === 1
                  ? '1 nodo decide el cierre del curso'
                  : `${criticalCount} nodos deciden el cierre del curso`}
              </span>
            </>
          )}
        </div>
      )}

      {/* ── Preview modal ──────────────────────────────────── */}
      {previewNodeId && (
        <NodePreview
          nodeId={previewNodeId}
          nodeTitle={draft.find((n) => n.id === previewNodeId)?.title ?? 'Nodo'}
          open={!!previewNodeId}
          onClose={() => setPreviewNodeId(null)}
          origin={previewOrigin}
        />
      )}
    </div>
  )
}
