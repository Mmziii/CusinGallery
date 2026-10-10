import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Dev-server proxy: the browser only ever talks to the Vite origin
 * (relative /api and /media URLs), and Vite forwards those to the
 * Django backend. Keeps session cookies + CSRF on a single origin and
 * means no CORS configuration is needed for day-to-day development.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Allows `npm run dev -- --host` / Docker port mapping to work without
    // Vite refusing connections from outside the container.
    host: true,
    // Preview tunnels (e.g. https://{port}-{sandbox}.e2b.app) reach the dev
    // server through a proxy, but Vite rejects requests whose Host header it
    // does not recognise with 403 "Blocked request", so the whole page fails
    // to load behind such a tunnel. A leading dot allows every subdomain;
    // localhost/127.0.0.1 keep plain local development working. Override with
    // VITE_ALLOWED_HOSTS="host1,host2" for any other tunnel domain.
    // (Dev-server setting only -- it never affects the production build.)
    allowedHosts: (process.env.VITE_ALLOWED_HOSTS || ".e2b.app,localhost,127.0.0.1").split(","),
    proxy: {
      // changeOrigin is deliberately OFF: Django must see the ORIGINAL
      // Host header (the preview/external origin) so ALLOWED_HOSTS
      // checks and request.build_absolute_uri() (used to build the
      // payment callback URL) reflect the origin the browser is on,
      // not the internal proxy target.
      "/api": {
        target: "http://localhost:8000",
      },
      "/media": {
        target: "http://localhost:8000",
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  // `npm test` = vitest run (see package.json). The smoke test renders the
  // real app root in jsdom with a fake axios adapter (src/test/setup.js).
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["src/test/setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
  },
});
