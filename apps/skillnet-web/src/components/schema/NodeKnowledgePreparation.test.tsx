import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NodeKnowledgePreparation } from './NodeKnowledgePreparation'
import type { NodeKnowledgePack } from '../../types'

/**
 * "Ver base pedagógica" — what the generator understood about one node.
 *
 * The disclosure exists so an admin can see why a lesson came out the way it did. It
 * used to dump `pack.markdown` into a `<pre>`: frontmatter, `## Debe conservarse`,
 * `### \`atom_3\` · concept`, `Fuentes:` lines and all. These tests hold the line that
 * only the atoms' sentences reach the screen.
 *
 * The sample below is shaped exactly like the server emitter's output
 * (`apps/skillnet-api/src/knowledge_pack/markdown.py`), because that is the only
 * contract the parsing has.
 */

const MARKDOWN = `---
format: knowledge_pack/v1
node_id: node-1
status: ready
canonical_hash: 9f1c
source_bundle_hash: 4ab2
semantic_hash: 77de
---

# Cómo se forma un hábito

## Objetivo

obj_habito_bucle

## Debe conservarse

### \`atom_1\` · concept · crítico

Un hábito se forma cuando una señal, una rutina y una recompensa se repiten juntas.

Fuentes: \`src_1\`, \`src_2\` · evidencia: \`ev_1\`

### \`atom_2\` · fact

El bucle necesita semanas de repetición antes de automatizarse.

Fuentes: \`src_1\`

## Opciones de adaptación

### \`atom_3\` · example

Dejar las zapatillas junto a la puerta es una señal puesta a propósito.

Fuentes: \`src_2\`
Detalles: misiones: practice · presentaciones: text · etiquetas: cotidiano

## Evidencia

- \`ev_1\` (obligatoria): El aprendiz nombra las tres partes del bucle — \`atom_1\`

## Fuentes

- \`src_1\`: documento \`doc_a\`, Hábitos › El bucle, párrafo 3 (revisión \`r1\`)
`

function pack(overrides: Partial<NodeKnowledgePack> = {}): NodeKnowledgePack {
  return {
    id: 'pack-1',
    node_id: 'node-1',
    status: 'ready',
    generator_version: 'v1',
    pack_hash: '9f1c',
    markdown: MARKDOWN,
    atom_count: 3,
    invariant_count: 2,
    required_evidence_count: 1,
    blocking_gaps: [],
    input_tokens: 100,
    output_tokens: 200,
    duration_ms: 1200,
    error_message: null,
    updated_at: '2026-08-27T10:00:00Z',
    ...overrides,
  }
}

/** The sentences the disclosure put on screen, in order. */
function sentences() {
  return screen.getAllByRole('listitem').map((item) => item.textContent)
}

describe('NodeKnowledgePreparation — the learning base disclosure', () => {
  it('shows every atom as a sentence, in the order the server emitted them', () => {
    render(<NodeKnowledgePreparation pack={pack()} loading={false} />)

    expect(screen.getByText('Ver base pedagógica')).toBeInTheDocument()
    expect(sentences()).toEqual([
      'Un hábito se forma cuando una señal, una rutina y una recompensa se repiten juntas.',
      'El bucle necesita semanas de repetición antes de automatizarse.',
      'Dejar las zapatillas junto a la puerta es una señal puesta a propósito.',
    ])
  })

  it('leaves the machine scaffolding out: ids, section headings, provenance, frontmatter', () => {
    const { container } = render(<NodeKnowledgePreparation pack={pack()} loading={false} />)
    const shown = container.textContent ?? ''

    for (const scaffold of [
      'atom_1', 'atom_2', 'atom_3', 'concept', 'crítico',
      'Debe conservarse', 'Opciones de adaptación', 'Objetivo', 'Evidencia', 'Fuentes',
      'Detalles', 'src_1', 'ev_1', 'canonical_hash', 'semantic_hash', 'obj_habito_bucle',
    ]) {
      expect(shown).not.toContain(scaffold)
    }
    // And nothing of the raw dump survives as a block of Markdown.
    expect(container.querySelector('pre')).toBeNull()
  })

  it('offers the disclosure on a pack that needs review, next to the gaps', () => {
    render(
      <NodeKnowledgePreparation
        pack={pack({ status: 'review_required', blocking_gaps: ['Falta la definición de recompensa.'] })}
        loading={false}
      />,
    )

    expect(screen.getByText('Ver base pedagógica')).toBeInTheDocument()
    expect(screen.getByText('Falta la definición de recompensa.')).toBeInTheDocument()
  })

  it('does not offer it while the pack is still being prepared, or when it failed', () => {
    const { unmount } = render(<NodeKnowledgePreparation pack={undefined} loading={true} />)
    expect(screen.queryByText('Ver base pedagógica')).not.toBeInTheDocument()
    unmount()

    render(<NodeKnowledgePreparation pack={pack({ status: 'failed', markdown: null })} loading={false} />)
    expect(screen.queryByText('Ver base pedagógica')).not.toBeInTheDocument()
  })

  it('does not offer it when the pack is ready but carries no readable atom', () => {
    // A pack whose Markdown is only its header sections has nothing to show, and an empty
    // disclosure is a promise of detail that is not there.
    render(<NodeKnowledgePreparation pack={pack({ markdown: '---\nnode_id: node-1\n---\n\n# Título\n\n## Evidencia\n' })} loading={false} />)
    expect(screen.queryByText('Ver base pedagógica')).not.toBeInTheDocument()
  })

  it('never hands a provenance line to the reader as if it were the sentence', () => {
    // `_line(atom.text)` can come out empty, and then `Fuentes:` is the first body line
    // of the block. It is still not prose.
    const markdown = [
      '## Debe conservarse',
      '',
      '### `atom_1` · concept',
      '',
      '',
      'Fuentes: `src_1`',
      '',
      '### `atom_2` · fact',
      '',
      'Una frase que sí existe.',
      '',
      'Fuentes: `src_1`',
      '',
    ].join('\n')

    render(<NodeKnowledgePreparation pack={pack({ markdown })} loading={false} />)
    expect(sentences()).toEqual(['Una frase que sí existe.'])
  })
})
