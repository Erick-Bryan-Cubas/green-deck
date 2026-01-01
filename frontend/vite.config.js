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
    emptyOutDir: true
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:3000'
    }
  }
})
