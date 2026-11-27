import { defineConfig } from 'vite'
export default defineConfig({
  resolve: { dedupe: ['three'] },
  server: {
    fs: { allow: ['.', '../../companion/frontend/src/engine', '../../companion/character-design/qingyi/expression-decals/stickers.json'] },
    proxy: { '/api': 'http://127.0.0.1:8601' },
  },
  build: { rollupOptions: { input: { index: 'index.html', 'torso-study': 'torso-study.html' } } }
})
