import type { Preview } from '@storybook/react-vite'
import { IntlProvider } from 'react-intl'
import { es } from '../src/i18n/es'
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

  /**
   * A toolbar toggle for the two surfaces a block actually lives on:
   *
   * - `app` — the white `main` of the admin/employee shell (the default; how the
   *   kit has always been reviewed).
   * - `theater` — the dark, focused course canvas (fullscreen NodeView), centred
   *   to `--lesson-measure`. This is the Brilliant-style lesson surface; flip to
   *   it to judge a block the way a learner sees it inside a lesson.
   */
  globalTypes: {
    surface: {
      description: 'Surface the block sits on',
      defaultValue: 'app',
      toolbar: {
        title: 'Surface',
        icon: 'browser',
        items: [
          { value: 'app', title: 'App (light)' },
          { value: 'theater-dark', title: 'Lesson (dark)' },
          { value: 'theater-light', title: 'Lesson (light)' },
        ],
        dynamicTitle: true,
      },
    },
  },

  decorators: [
    /**
     * IntlProvider wraps all stories because most components (ClickableText,
     * QuizItemBlock, DragOrderBlock, etc.) call `useIntl()`. Without it the story
     * crashes immediately with "Could not find required `intl` object".
     *
     * The surface decorator then puts the story on the chosen ground: the light
     * app `main`, or the dark lesson theater centred to the reading measure.
     */
    (Story, context) => {
      const surface = context.globals.surface
      const theaterMode =
        surface === 'theater-dark' ? 'mode-dark' : surface === 'theater-light' ? 'mode-light' : null
      return (
        <IntlProvider locale="es" messages={es} defaultLocale="es">
          {theaterMode ? (
            <div className={`lesson-theater ${theaterMode} min-h-screen flex items-center justify-center p-8`}>
              <div className="w-full flex flex-col gap-6" style={{ maxWidth: 'var(--lesson-measure)' }}>
                <Story />
              </div>
            </div>
          ) : (
            <div className="bg-bg text-text min-h-screen p-4">
              <Story />
            </div>
          )}
        </IntlProvider>
      )
    },
  ],
};

export default preview;
