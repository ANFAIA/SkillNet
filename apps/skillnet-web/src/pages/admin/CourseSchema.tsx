import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, EmptyState, Skeleton, SkeletonText } from '../../components/ui'
import { CriticalityBadge } from '../../components/schema/CriticalityBadge'
import { IntentDensitySlider } from '../../components/schema/IntentDensitySlider'
import { NodeEditor, type DraftNode } from '../../components/schema/NodeEditor'
import { ReviewChecklist } from '../../components/schema/ReviewChecklist'
import { SchemaValidationPanel } from '../../components/schema/SchemaValidationPanel'
import type { PrerequisiteOption } from '../../components/schema/PrerequisitePicker'
import { useCourse } from '../../api/courses'
import { NodePreview } from '../../components/schema/NodePreview'
import {
  isSchemaSurfaceDisabled,
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
 * The creator's gate (§3.2, §11.1).
 *
 * This screen is the only place a course schema becomes servable, and everything on it
 * exists to make that irreversible-feeling step legible:
 *
 * - **Nothing is generated until validation.** The banner says so in those words,
 *   because the promise of §1.1 is that no learner ever receives generated content for
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

  const [draft, setDraft] = useState<DraftNode[]>([])
  const [density, setDensity] = useState(3)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
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
    // Selected in the same pass as the draft, so the editor is on screen in the first
    // render that has nodes rather than one render later.
    setSelectedKey((previous) =>
      server.nodes.some((node) => node.id === previous)
        ? previous
        : (server.nodes[0]?.id ?? null),
    )
  }, [server, signature])

  useEffect(() => {
    if (draft.length === 0) {
      if (selectedKey !== null) setSelectedKey(null)
      return
    }
    if (!draft.some((node) => node.key === selectedKey)) setSelectedKey(draft[0].key)
  }, [draft, selectedKey])

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
  const unreviewedCount = liveNodes.filter((node) => {
    const stamped = node.id ? serverById.get(node.id)?.reviewed_at : null
    return !stamped || dirtyByKey.get(node.key)
  }).length

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

  function moveNode(key: string, direction: -1 | 1) {
    setDraft((prev) => {
      const index = prev.findIndex((node) => node.key === key)
      const target = index + direction
      if (index < 0 || target < 0 || target >= prev.length) return prev
      const next = [...prev]
      const [moved] = next.splice(index, 1)
      next.splice(target, 0, moved)
      return next
    })
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
        // Inherited so a hand-made node satisfies the "no source, no course" rule
        // without the creator having to know it exists.
        sourceDocumentId: courseQuery.data?.source_document_id ?? null,
        sourceHeadings: [],
        prerequisiteNodeIds: [],
        archived: false,
      },
    ])
    setSelectedKey(key)
  }

  function removeNode(key: string) {
    setDraft((prev) => {
      const removed = prev.find((node) => node.key === key)
      const next = prev.filter((node) => node.key !== key)
      // A removed node also stops being anybody's prerequisite, otherwise the next
      // save would ask the server to validate an edge to a node that is gone.
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
  }

  /**
   * Unvalidating is the fix for `schema_locked`, so it clears that notice on success —
   * otherwise the alert telling the creator to unvalidate would still be on screen
   * after they did.
   */
  function unvalidate() {
    unvalidateSchema.mutate(undefined, { onSuccess: () => updateSchema.reset() })
  }

  function save() {
    // Rule violations from a previous validate describe a schema that no longer
    // exists once this save lands.
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

  if (schemaQuery.isLoading) {
    return (
      <div>
        <Skeleton className="h-6 w-1/3 mb-6" />
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="w-full lg:w-80 lg:shrink-0">
            <Card>
              <SkeletonText lines={5} />
            </Card>
          </div>
          <div className="flex-1 min-w-0">
            <Card>
              <SkeletonText lines={8} />
            </Card>
          </div>
        </div>
      </div>
    )
  }

  if (schemaQuery.error || !server) {
    return isSchemaSurfaceDisabled(schemaQuery.error) ? (
      <EmptyState
        title="Los cursos dinamicos estan desactivados"
        description="Esta pantalla necesita DYNAMIC_COURSES_MODE en 'shadow' o 'on'. Mientras este apagada, los cursos siguen el flujo clasico de modulos y lecciones."
        action={{ label: 'Volver a contenido', onClick: () => navigate('/admin/contenido') }}
      />
    ) : (
      <EmptyState
        title="No se pudo cargar el esquema"
        description="Vuelve a intentarlo en unos segundos."
        action={{ label: 'Reintentar', onClick: () => void schemaQuery.refetch() }}
      />
    )
  }

  const selected = draft.find((node) => node.key === selectedKey) ?? null
  const selectedIndex = selected ? draft.findIndex((node) => node.key === selected.key) : -1

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

  const prerequisiteOptions: PrerequisiteOption[] = draft.flatMap((node, index) =>
    node.key === selectedKey || node.archived
      ? []
      : [{ id: node.id, key: node.key, position: index + 1, title: node.title }],
  )

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => navigate('/admin/contenido')}>
            ← Contenido
          </Button>
          {/* The schema screen is reached from the course as often as from the list, and
              without this the only way back to the course was the browser's back button. */}
          <Button variant="ghost" size="sm" onClick={() => navigate(`/admin/curso/${id}`)}>
            ← Volver al curso
          </Button>
        </div>

        <div className="flex items-center gap-3 mt-1 min-w-0">
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
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="w-full lg:w-80 lg:shrink-0 space-y-5">
            <ReviewChecklist
              items={draft.map((node, index) => ({
                key: node.key,
                id: node.id,
                position: index + 1,
                title: node.title,
                criticality: node.criticality,
                reviewedAt: node.id ? serverById.get(node.id)?.reviewed_at ?? null : null,
                archived: node.archived,
                dirty: !!dirtyByKey.get(node.key),
              }))}
              selectedKey={selectedKey}
              onSelect={setSelectedKey}
              onMarkReviewed={(nodeId) => markReviewed.mutate(nodeId)}
              pendingNodeId={markReviewed.isPending ? markReviewed.variables ?? null : null}
              locked={!!locked}
            />

            <Card>
              <IntentDensitySlider
                value={density}
                onChange={setDensity}
                disabled={locked || proposeJob.running}
              />
              <div className="flex flex-wrap items-center gap-2 mt-4">
                <Button variant="secondary" size="sm" onClick={addNode} disabled={locked}>
                  Anadir nodo
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={propose}
                  disabled={locked || proposeSchema.isPending || proposeJob.running}
                >
                  {proposeJob.running || proposeSchema.isPending
                    ? 'Proponiendo...'
                    : 'Volver a proponer'}
                </Button>
              </div>
              <p className="text-xs text-text-muted mt-2">
                Volver a proponer reemplaza los nodos propuestos por una tanda nueva.
              </p>
            </Card>
          </div>

          <div className="flex-1 min-w-0">
            <Card>
              {selected && selectedIndex >= 0 ? (
                <>
                  <NodeEditor
                    node={selected}
                    index={selectedIndex}
                    total={draft.length}
                    prerequisiteOptions={prerequisiteOptions}
                    reviewedAt={
                      selected.id ? serverById.get(selected.id)?.reviewed_at ?? null : null
                    }
                    dirty={!!dirtyByKey.get(selected.key)}
                    locked={!!locked}
                    onChange={(patch) => patchNode(selected.key, patch)}
                    onMove={(direction) => moveNode(selected.key, direction)}
                    onArchiveToggle={() =>
                      patchNode(selected.key, { archived: !selected.archived })
                    }
                    onRemove={() => removeNode(selected.key)}
                  />
                  {selected.id && !dirtyByKey.get(selected.key) && (
                    <div className="mt-4 pt-4 border-t border-border">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={(e) => {
                          setPreviewOrigin(e.currentTarget.getBoundingClientRect())
                          setPreviewNodeId(selected.id)
                        }}
                      >
                        Previsualizar contenido
                      </Button>
                      <p className="text-xs text-text-muted mt-1.5">
                        Genera el contenido como lo veria un empleado.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <EmptyState
                  title="Selecciona un nodo"
                  description="Elige un nodo de la lista para revisarlo y editarlo."
                />
              )}
            </Card>
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-8 pt-4 border-t border-border">
        {/* The set of live `critical` nodes is exactly the course closure condition
            (§7.5), so the creator sees its size next to the button that freezes it. */}
        <div className="flex items-center gap-2 min-w-0">
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
        <div className="flex items-center gap-2 flex-wrap">
          {validateBlockedReason && !locked && (
            <span className="text-xs text-text-muted">{validateBlockedReason}</span>
          )}
          <Button
            variant="secondary"
            onClick={save}
            disabled={locked || !dirty || updateSchema.isPending}
          >
            {updateSchema.isPending ? 'Guardando...' : 'Guardar cambios'}
          </Button>
          <Button
            variant="accent"
            onClick={() => validateSchema.mutate()}
            disabled={!!validateBlockedReason || validateSchema.isPending}
            title={validateBlockedReason ?? 'Activa la entrega dinamica de este curso'}
          >
            {validateSchema.isPending ? 'Validando...' : 'Validar esquema'}
          </Button>
        </div>
      </div>

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
