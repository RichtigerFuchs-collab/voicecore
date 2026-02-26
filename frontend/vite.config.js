import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,   // bindet auf 0.0.0.0 → kein ERR_CONNECTION_REFUSED auf Windows
    port: 5173,
  },
})
