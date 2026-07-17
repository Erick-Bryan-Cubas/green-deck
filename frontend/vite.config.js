import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // Remove console.* e debugger apenas no build de produção
  // (em dev os logs continuam disponíveis para depuração)
  esbuild: command === 'build' ? { drop: ['console', 'debugger'] } : undefined,
  // Configuração necessária para @tato30/vue-pdf (PDF.js)
  optimizeDeps: {
    include: ['pdfjs-dist']
  },
  // O worker do PDF.js (pdf.worker.min.mjs?worker) é um módulo ES — o formato
  // 'iife' padrão falharia ao empacotá-lo
  worker: {
    format: 'es'
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('pdfjs-dist')) return 'pdf-worker'
            if (id.includes('vue-pdf') || id.includes('@tato30')) return 'pdf-viewer'
            if (id.includes('primevue') || id.includes('primeuix')) return 'primevue'
            if (id.includes('chart.js')) return 'chart'
            if (id.includes('quill')) return 'editor'
            if (id.includes('vue-router')) return 'vue-router'
            if (id.includes('vue')) return 'vue'
          }
        }
      }
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:3000',
        // Sem isso, um ECONNRESET (backend fora do ar ou cliente que fecha
        // a conexão no meio da request) derruba o dev server inteiro.
        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.warn('[vite proxy] /api indisponível:', err.code || err.message)
          })
        }
      }
    }
  }
}))
