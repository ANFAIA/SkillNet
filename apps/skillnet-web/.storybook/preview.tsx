import type { Preview } from '@storybook/react-vite'
import '../src/index.css'

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
       color: /(background|color)$/i,
       date: /Date$/i,
      },
    },

    a11y: {
      // 'todo' - show a11y violations in the test UI only
      // 'error' - fail CI on a11y violations
      // 'off' - skip a11y checks entirely
      test: 'todo'
    }
  },
  decorators: [
    /**
     * Put every story on the surface it actually lives on.
     *
     * `src/index.css` paints `body` with the L-frame blue gradient, and Storybook
     * imports that file, so the canvas was the gradient — while in the app every one
     * of these components sits inside the white `main`. Judging a Callout's tint or a
     * Table's borders against a dark blue is judging the wrong picture, and the block
     * stories are the thing the kit is reviewed on.
     */
    (Story) => (
      <div className="bg-bg text-text min-h-screen p-4">
        <Story />
      </div>
    ),
  ],
};

export default preview;
