import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png', 'icons.svg'],
      manifest: {
        name: 'PrimeFit',
        short_name: 'PrimeFit',
        description: 'AI-powered fitness assistant, workout tracker, and Filipino nutrition log.',
        theme_color: '#15171b',
        background_color: '#15171b',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // SPA fallback: any unmatched navigation (e.g. a hard refresh on
        // /workouts/templates/3 while offline) serves the cached app shell.
        navigateFallback: '/index.html',
        runtimeCaching: [
          {
            // Django backend API -- match by path so it works regardless of
            // which host VITE_API_BASE_URL points at (localhost in dev,
            // a real API domain in prod).
            urlPattern: ({ url, sameOrigin }) =>
              !sameOrigin &&
              /^\/(accounts|workouts|nutrition|coach|progress)\//.test(url.pathname),
            handler: 'NetworkFirst',
            method: 'GET',
            options: {
              cacheName: 'primefit-api',
              networkTimeoutSeconds: 8,
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 }, // 1 day
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\//,
            handler: 'StaleWhileRevalidate',
            options: { cacheName: 'google-fonts-stylesheets' },
          },
          {
            urlPattern: /^https:\/\/fonts\.gstatic\.com\//,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-webfonts',
              expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: {
        // Lets you test the service worker with `npm run dev` too, not just
        // production builds.
        enabled: true,
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
  },
})
