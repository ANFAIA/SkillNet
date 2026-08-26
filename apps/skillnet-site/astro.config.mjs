import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  // Absolute canonical/hreflang URLs need the production origin at build time.
  // Without it Astro falls back to the dev origin and every alternate link in
  // dist/ pointed at http://localhost:4321, which is useless to a crawler.
  site: "https://skillnet.es",
  integrations: [react()],
  vite: {
    plugins: [tailwindcss()],
  },
  i18n: {
    defaultLocale: "es",
    locales: ["es", "en"],
    routing: {
      prefixDefaultLocale: false,
    },
  },
});
