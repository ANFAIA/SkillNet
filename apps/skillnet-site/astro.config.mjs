import { defineConfig } from 'astro/config'

export default defineConfig({
  site: 'https://skillnet.es',
  output: 'static',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
})
