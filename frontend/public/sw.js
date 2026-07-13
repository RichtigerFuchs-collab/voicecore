// VoiceCore Service Worker
// Zweck: App-Oberfläche aus dem Cache öffnen, auch wenn der Render-Server
// gerade schläft (Cold Start ~40 s). Strategie: stale-while-revalidate –
// sofort aus dem Cache antworten, im Hintergrund frische Version holen
// (steht dann beim nächsten Öffnen bereit).
// /upload und /health gehen IMMER ans Netz (nie cachen!).

const CACHE = 'voicecore-shell-v1'

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  // Nur GET-Requests an den eigenen Origin cachen, API-Routen ausnehmen
  if (
    event.request.method !== 'GET' ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith('/upload') ||
    url.pathname.startsWith('/health')
  ) {
    return // Browser-Standardverhalten
  }

  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request)
      const network = fetch(event.request)
        .then((resp) => {
          if (resp.ok) cache.put(event.request, resp.clone())
          return resp
        })
        .catch(() => cached) // offline/schlafend: Cache ist die Antwort

      // Cache sofort liefern (App öffnet ohne Wartezeit), sonst Netz
      return cached || network
    })
  )
})
