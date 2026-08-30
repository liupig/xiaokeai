import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig, type Plugin } from 'vite';

const BACKEND = 'http://127.0.0.1:8600';
const root = dirname(fileURLToPath(import.meta.url));

/** 把 Silero VAD / ONNX Runtime 的 worklet、模型、wasm 拷到 public/vad，供开麦 ASR 使用 */
function vadAssetsPlugin(): Plugin {
  const copy = () => {
    const dest = resolve(root, 'public/vad');
    mkdirSync(dest, { recursive: true });
    const files: [string, string][] = [
      ['node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', 'vad.worklet.bundle.min.js'],
      ['node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', 'silero_vad_v5.onnx'],
      ['node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', 'silero_vad_legacy.onnx'],
      ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.wasm'],
      ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.mjs'],
    ];
    for (const [from, name] of files) {
      const src = resolve(root, from);
      if (!existsSync(src)) {
        console.warn(`[vad-assets] missing ${from}`);
        continue;
      }
      copyFileSync(src, resolve(dest, name));
    }
  };
  return {
    name: 'vad-assets',
    configResolved: copy,
  };
}

export default defineConfig({
  plugins: [vue(), vadAssetsPlugin()],
  optimizeDeps: {
    exclude: ['@mediapipe/tasks-vision'],
    include: ['@ricky0123/vad-web', 'onnxruntime-web', 'onnxruntime-web/wasm', '@ennuicastr/webrtcaec3.js'],
    esbuildOptions: { target: 'es2020' },
  },
  build: { target: 'es2020' },
  worker: {
    format: 'iife',
  },
  server: {
    port: 5175,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true, timeout: 600000 },
      '/assets': { target: BACKEND, changeOrigin: true },
      '/keepsakes': { target: BACKEND, changeOrigin: true },
    },
  },
});
