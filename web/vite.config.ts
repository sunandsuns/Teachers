import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 后端地址可被 run.py 通过 VITE_API_TARGET 覆盖（后端换端口时用）。
// 默认用 127.0.0.1 而非 localhost：后端显式绑定 IPv4，而 localhost 可能先解析到 ::1，
// 那样代理会连不上。
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 开发环境代理到后端，避免 CORS 问题
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
