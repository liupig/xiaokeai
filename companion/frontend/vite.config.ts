import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig, type Plugin } from 'vite';

const BACKEND = 'http://127.0.0.1:8600';
const root = dirname(fileURLToPath(import.meta.url));

/** 把开麦要用的静态资源拷到 public：VAD/ONNX，以及不能打进 ES 模块的 AEC3 */
function voiceAssetsPlugin(): Plugin {
  const copy = () => {
    const groups: { dest: string; files: [string, string][] }[] = [
      {
        dest: 'public/vad',
        files: [
          ['node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', 'vad.worklet.bundle.min.js'],
          ['node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', 'silero_vad_v5.onnx'],
          ['node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', 'silero_vad_legacy.onnx'],
          ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.wasm'],
          ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.mjs'],
        ],
      },
      {
        dest: 'public/aec3',
        files: [
          ['node_modules/@ennuicastr/webrtcaec3.js/dist/webrtcaec3-0.3.0.js', 'webrtcaec3-0.3.0.js'],
        ],
      },
    ];
    for (const group of groups) {
      const dest = resolve(root, group.dest);
      mkdirSync(dest, { recursive: true });
      for (const [from, name] of group.files) {
        const src = resolve(root, from);
        if (!existsSync(src)) {
          console.warn(`[voice-assets] missing ${from}`);
          continue;
        }
        copyFileSync(src, resolve(dest, name));
      }
    }
  };
  return {
    name: 'voice-assets',
    configResolved: copy,
  };
}

export default defineConfig({
  plugins: [vue(), voiceAssetsPlugin()],
  optimizeDeps: {
    exclude: ['@mediapipe/tasks-vision', '@ennuicastr/webrtcaec3.js'],
    esbuildOptions: { target: 'es2020' },
  },
  build: {
    target: 'es2020',
    assetsDir: 'static',
    minify: 'terser',
    terserOptions: {
      compress: { drop_console: true, drop_debugger: true },
      mangle: true,
    },
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/naive-ui')) return 'naive-ui';
          if (id.includes('@pixiv/three-vrm')) return 'three-vrm';
          if (id.includes('node_modules/three/') || id.includes('node_modules/three\\')
            || id.includes('three-stdlib')) return 'three';
          if (id.includes('@ricky0123/vad-web') || id.includes('onnxruntime')) return 'vad';
          if (id.includes('node_modules/mediabunny')) return 'mediabunny';
        },
      },
    },
  },
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
