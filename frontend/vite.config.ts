import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiRoutes = [
  '/jobs.json',
  '/choose-file',
  '/choose-directory',
  '/generate-english',
  '/translate-ai',
  '/preview-frame',
  '/preview',
  '/finalize',
  '/process',
  '/edit',
  '/save-manual',
  '/shutdown',
]

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../video_tool/static',
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: Object.fromEntries(
      apiRoutes.map((route) => [route, { target: 'http://127.0.0.1:8876', changeOrigin: false }]),
    ),
  },
})
