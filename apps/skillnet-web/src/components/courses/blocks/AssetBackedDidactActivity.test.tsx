import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { DidactHostPorts } from '../../../lib/didact'
import { AssetBackedDidactActivity } from './AssetBackedDidactActivity'

vi.mock('../../../lib/didact', () => ({
  DidactComponentMount: ({ componentProps }: { componentProps: { media?: ReactNode } }) => (
    <div data-testid="mounted-asset">{componentProps.media}</div>
  ),
}))

function ports(resolve: NonNullable<DidactHostPorts['assets']>): DidactHostPorts {
  return { assets: resolve }
}

describe('AssetBackedDidactActivity', () => {
  it('loads images lazily and uses server accessibility metadata', async () => {
    const resolve = vi.fn().mockResolvedValue({
      ref: 'skasset_opaque',
      url: '/api/v1/media/artifacts/asset/asset',
      mimeType: 'image/png',
      alt: 'Diagrama accesible',
      longDescription: 'Descripción larga',
      width: 1200,
      height: 800,
    })
    render(
      <AssetBackedDidactActivity
        activityId="activity"
        componentId="didact.hotspot"
        componentProps={{ assetRef: 'skasset_opaque', regions: [] }}
        ports={ports({ resolve })}
      />,
    )

    const image = await screen.findByRole('presentation')
    expect(image).toHaveAttribute('src', '/api/v1/media/artifacts/asset/asset')
    expect(image).toHaveAttribute('loading', 'lazy')
    expect(image).toHaveAttribute('decoding', 'async')
    expect(resolve).toHaveBeenCalledWith(
      'skasset_opaque',
      { organizationId: '', courseId: '' },
      expect.any(AbortSignal),
    )
  })

  it('fails closed when an asset is missing', async () => {
    render(
      <AssetBackedDidactActivity
        activityId="activity"
        componentId="didact.hotspot"
        componentProps={{ assetRef: 'skasset_missing' }}
        ports={ports({ resolve: vi.fn().mockRejectedValue(new Error('404')) })}
      />,
    )
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('No se pudo resolver')
    })
    expect(screen.queryByTestId('mounted-asset')).not.toBeInTheDocument()
  })
})
