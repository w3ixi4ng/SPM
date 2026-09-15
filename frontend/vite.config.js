import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Vite serves the app and forwards /api to Kong, so the browser only ever
  // sees one origin: localhost:5173. That is what makes the session cookies
  // work -- a direct call to another port would be cross-origin, which needs
  // CORS with credentials and a weaker SameSite. In production Kong fronts
  // both and this proxy is not used.
  //
  // No rewrite: Kong's routes are defined on /api, so the prefix stays.
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  plugins: [react(), tailwindcss()],
})
