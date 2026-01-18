import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // Configuração necessária para @tato30/vue-pdf (PDF.js)
  optimizeDeps: {
    include: ['pdfjs-dist']
  },
  build: {
    outDir: '../static/dist',
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
      '/api': 'http://127.0.0.1:3000'
    }
  }
})
