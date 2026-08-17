/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';
import { playwright } from '@vitest/browser-playwright';
const dirname = typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url));

// More info at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@didact/ui': path.resolve(dirname, 'src/lib/didact/vendor-entrypoints/ui.ts'),
      '@didact/schema': path.resolve(dirname, 'src/lib/didact/vendor-entrypoints/schema.ts'),
      '@didact/spaced-repetition': path.resolve(dirname, 'src/lib/didact/vendor-entrypoints/spaced-repetition.ts'),
    },
  },
  server: {
    proxy: {
      '/api': process.env.SKILLNET_API_PROXY ?? 'http://127.0.0.1:8000',
    },
  },
  test: {
    // Cap worker parallelism. The default (one worker per CPU) oversubscribes this host:
    // jsdom + framer-motion across ~65 files saturate the CPU, and correct tests that run
    // in ~1s in isolation then blow the default 5s timeout under contention — the flaky
    // "610/614, passes in isolation" failures. Half the cores keeps throughput while
    // leaving headroom so timings stay honest.
    maxWorkers: '50%',
    projects: [
      // Unit tests — jsdom, fast, no browser
      {
        extends: true,
        test: {
          name: 'unit',
          environment: 'jsdom',
          include: ['src/**/*.test.{ts,tsx}'],
          setupFiles: ['src/test/setup.ts'],
          // Generous enough that a slow-but-correct test under load does not fail; a real
          // hang still trips it. Paired with the worker cap above.
          testTimeout: 15000,
          hookTimeout: 15000,
          // A couple of async-mount tests (Didact) assert with `getBy` on a component that
          // finishes mounting a tick later; under full-suite CPU load that tick slips and
          // the element is momentarily null — they pass alone and when re-run. One retry
          // absorbs that load-timing jitter without hiding a real break: a deterministic
          // failure still fails every attempt.
          retry: 1,
        },
      },
      // Storybook interaction tests — browser via Playwright
      {
        extends: true,
        plugins: [
        // The plugin will run tests for the stories defined in your Storybook config
        // See options at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon#storybooktest
        storybookTest({
          configDir: path.join(dirname, '.storybook')
        })],
        test: {
          name: 'storybook',
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{
              browser: 'chromium'
            }]
          }
        }
      },
    ]
  }
});
