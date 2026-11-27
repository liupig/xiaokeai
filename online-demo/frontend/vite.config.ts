import { defineConfig } from 'vite'
export default defineConfig({
  resolve: { dedupe: ['three'] },
  server: {
    fs: { allow: ['.', '../../companion/frontend/src/engine'] },
    proxy: { '/api': 'http://127.0.0.1:8601' },
  },
  build: { rollupOptions: { input: { index: 'index.html', 'torso-study': 'torso-study.html' } } }
})
