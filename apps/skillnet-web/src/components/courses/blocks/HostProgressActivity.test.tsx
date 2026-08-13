import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DidactHostPorts } from '../../../lib/didact'
import { HostProgressActivity } from './HostProgressActivity'

vi.mock('../../../lib/didact', () => ({
  DidactComponentMount: ({ componentProps }: { componentProps: Record<string, unknown> }) => (
    <div data-testid="mounted">{JSON.stringify(componentProps)}</div>
  ),
}))

describe('HostProgressActivity', () => {
  it('injects server-owned percent and ignores authored values', async () => {
    const ports: DidactHostPorts = {
      progress: {
        async read() {
          return {
            scope: { organizationId: '', courseId: '' },
            componentId: 'didact.progress',
            status: 'in_progress',
            progress: 42,
            evidence: { level: 'intermediate' },
          }
        },
        async write() {
          throw new Error('progress_is_server_owned')
        },
      },
    }

    render(
      <HostProgressActivity
        activityId="activity-1"
        componentId="didact.progress"
        componentProps={{ kind: 'lesson', label: 'Lección', value: 99 }}
        ports={ports}
      />,
    )

    expect(await screen.findByTestId('mounted')).toHaveTextContent('"value":42')
    expect(screen.getByTestId('mounted')).not.toHaveTextContent('"value":99')
  })
})
