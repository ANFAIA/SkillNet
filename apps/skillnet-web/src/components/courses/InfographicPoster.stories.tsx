import type { Meta, StoryObj } from '@storybook/react-vite'
import { InfographicPoster } from './InfographicPoster'

const meta = {
  title: 'Courses/InfographicPoster',
  component: InfographicPoster,
  parameters: {
    layout: 'fullscreen',
    a11y: { test: 'error' },
  },
  decorators: [
    (Story) => (
      <main className="min-h-screen bg-bg-subtle p-6">
        <div className="mx-auto max-w-xl">
          <Story />
        </div>
      </main>
    ),
  ],
} satisfies Meta<typeof InfographicPoster>

export default meta
type Story = StoryObj<typeof meta>

export const Generada: Story = {
  args: {
    src: '/infographic-art/phishing-response.png',
    title: 'Ante un correo sospechoso',
  },
}
