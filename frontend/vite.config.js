import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Send every /api request to Django, so React and Django
    // look like one website to the browser.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})