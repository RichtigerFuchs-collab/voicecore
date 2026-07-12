import { useState, useRef, useEffect } from 'react'

// ─── Konstanten ───────────────────────────────────────────────────────────────

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TEMPLATES = [
  { id: 'tagebuch',          label: 'Tagebuch' },
  { id: 'quick_note',        label: 'Quick Note' },
  { id: 'restaurant_review', label: 'Restaurant Review' },
]

const SPEAKERS = ['Kim', 'Kathrin']

// Safari unterstützt kein audio/webm, aber audio/mp4.
// Chrome/Android nimmt audio/webm;codecs=opus.
// Wir prüfen zur Laufzeit, was der Browser kann.
function getSupportedMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',  // Chrome/Android: beste Qualität
    'audio/webm',              // Chrome/Android: Fallback
    'audio/mp4',               // Safari/iOS
    'audio/ogg;codecs=opus',   // Firefox Desktop
  ]
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return '' // absoluter Fallback: Browser entscheidet selbst
}

// ─── IndexedDB: letzte fehlgeschlagene Aufnahme aufbewahren ──────────────────
// localStorage kann keine Blobs und ist zu klein für Audio — IndexedDB schon.
// Ein einziger Slot ('last') reicht: die letzte nicht gesendete Aufnahme.

const DB_NAME = 'voicecore'
const STORE   = 'pending'

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror   = () => reject(req.error)
  })
}

async function savePending(rec) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(rec, 'last')
    tx.oncomplete = resolve
    tx.onerror    = () => reject(tx.error)
  })
}

async function loadPending() {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const req = db.transaction(STORE, 'readonly').objectStore(STORE).get('last')
    req.onsuccess = () => resolve(req.result || null)
    req.onerror   = () => reject(req.error)
  })
}

async function clearPendingDb() {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete('last')
    tx.oncomplete = resolve
    tx.onerror    = () => reject(tx.error)
  })
}

// ─── Status-Anzeige ───────────────────────────────────────────────────────────

const STATUS_MESSAGES = {
  idle:      '⬤  Bereit',
  recording: '◉  Aufnahme läuft...',
  uploading: '↑  Wird hochgeladen...',
  done:      '✓  Fertig!',
  error:     '✗  Fehler',
}

// ─── Haupt-Komponente ─────────────────────────────────────────────────────────

export default function App() {
  // Die State-Machine: idle → recording → uploading → done | error
  const [status, setStatus]     = useState('idle')
  const [template, setTemplate] = useState(TEMPLATES[0].id)
  const [result, setResult]     = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  const [speaker, setSpeaker] = useState(() =>
    localStorage.getItem('voicecore_speaker') || SPEAKERS[0]
  )

  const [appSecret, setAppSecret] = useState(() =>
    localStorage.getItem('voicecore_app_secret') || ''
  )

  // Nicht gesendete Aufnahme (überlebt auch App-Neustart via IndexedDB)
  const [pending, setPending] = useState(null)

  useEffect(() => {
    loadPending().then(rec => rec && setPending(rec)).catch(() => {})
  }, [])

  const [showSettings, setShowSettings] = useState(false)
  const [destinations, setDestinations] = useState(() => {
    try { return JSON.parse(localStorage.getItem('voicecore_destinations')) || {} }
    catch { return {} }
  })

  // Refs für Werte die kein Re-Render auslösen sollen
  const mediaRecorderRef = useRef(null)
  const audioChunksRef   = useRef([])

  // ── Destinations persistieren ────────────────────────────────────────────

  function updateDestination(templateId, url) {
    const updated = { ...destinations, [templateId]: url }
    setDestinations(updated)
    localStorage.setItem('voicecore_destinations', JSON.stringify(updated))
  }

  function selectSpeaker(name) {
    setSpeaker(name)
    localStorage.setItem('voicecore_speaker', name)
  }

  function updateAppSecret(value) {
    setAppSecret(value)
    localStorage.setItem('voicecore_app_secret', value)
  }

  // ── Aufnahme starten ─────────────────────────────────────────────────────

  async function startRecording() {
    setResult(null)
    setErrorMsg('')

    // Mikrofon-Erlaubnis anfordern — muss aus einem User-Gesture kommen (iOS!)
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err) {
      setErrorMsg('Mikrofon-Zugriff verweigert. Bitte in den Einstellungen erlauben.')
      setStatus('error')
      return
    }

    const mimeType = getSupportedMimeType()
    const options  = mimeType ? { mimeType } : {}

    const recorder = new MediaRecorder(stream, options)
    mediaRecorderRef.current = recorder
    audioChunksRef.current   = []

    // Audio-Daten sammeln
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunksRef.current.push(event.data)
    }

    // Wenn Aufnahme stoppt: Mikrofon-Icon ausblenden, Upload starten
    recorder.onstop = () => {
      stream.getTracks().forEach(track => track.stop())
      uploadAudio(audioChunksRef.current, mimeType)
    }

    recorder.start()
    setStatus('recording')
  }

  // ── Aufnahme stoppen ─────────────────────────────────────────────────────

  function stopRecording() {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop() // löst recorder.onstop aus
      setStatus('uploading')
    }
  }

  // ── Button-Klick: Toggle zwischen Start und Stop ─────────────────────────

  function handleButtonClick() {
    if (status === 'recording') {
      stopRecording()
    } else if (status === 'idle' || status === 'done' || status === 'error') {
      startRecording()
    }
    // Bei 'uploading': nichts tun
  }

  // ── Upload zum Backend ───────────────────────────────────────────────────

  async function sendRecording(blob, mimeType, templateId, speakerName) {
    const ext      = mimeType?.includes('mp4') ? 'm4a'
                   : mimeType?.includes('ogg') ? 'ogg'
                   : mimeType?.includes('wav') ? 'wav'
                   : 'webm'

    const formData = new FormData()
    formData.append('audio', blob, `recording.${ext}`)
    formData.append('template', templateId)
    formData.append('destination_url', destinations[templateId] || '')
    formData.append('speaker', speakerName)

    const response = await fetch(`${API_URL}/upload`, {
      method: 'POST',
      body: formData,
      // Content-Type NICHT manuell setzen — Browser setzt den multipart-Boundary
      headers: { 'X-App-Secret': appSecret },
    })

    if (response.status === 401) {
      throw new Error('Falsches oder fehlendes App-Passwort. Bitte im ⚙-Menü eintragen.')
    }
    if (!response.ok) throw new Error(`Server-Fehler: ${response.status}`)

    return response.json()
  }

  async function uploadAudio(chunks, mimeType) {
    const audioBlob = new Blob(chunks, { type: mimeType || 'audio/webm' })

    try {
      const data = await sendRecording(audioBlob, mimeType, template, speaker)
      setResult(data)
      setStatus('done')
    } catch (err) {
      // Aufnahme aufbewahren, damit sie nicht verloren geht
      const rec = { blob: audioBlob, mimeType, template, speaker, savedAt: Date.now() }
      try {
        await savePending(rec)
        setPending(rec)
        setErrorMsg(`${err.message} — die Aufnahme ist gespeichert, du kannst sie unten erneut senden.`)
      } catch {
        setErrorMsg(err.message)
      }
      setStatus('error')
    }
  }

  // ── Gespeicherte Aufnahme erneut senden / verwerfen ─────────────────────

  async function retryPending() {
    if (!pending || status === 'uploading' || status === 'recording') return
    setStatus('uploading')
    setErrorMsg('')
    setResult(null)

    try {
      const data = await sendRecording(pending.blob, pending.mimeType, pending.template, pending.speaker)
      await clearPendingDb().catch(() => {})
      setPending(null)
      setResult(data)
      setStatus('done')
    } catch (err) {
      setErrorMsg(err.message)
      setStatus('error')
    }
  }

  async function discardPending() {
    await clearPendingDb().catch(() => {})
    setPending(null)
  }

  // ── Render ───────────────────────────────────────────────────────────────

  const isRecording = status === 'recording'
  const isDisabled  = status === 'uploading'

  return (
    <div style={styles.page}>

      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.title}>VoiceCore</h1>
        <button
          onClick={() => setShowSettings(s => !s)}
          style={styles.gearButton}
          title="Einstellungen"
        >
          ⚙
        </button>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div style={styles.settingsPanel}>
          <p style={styles.settingsTitle}>App-Passwort</p>
          <div style={styles.settingsRow}>
            <input
              type="password"
              placeholder="einmal eintragen, wird gespeichert"
              value={appSecret}
              onChange={e => updateAppSecret(e.target.value)}
              style={styles.settingsInput}
              autoComplete="off"
            />
          </div>
          <p style={styles.settingsTitle}>Google Docs Ziele</p>
          {TEMPLATES.map(t => (
            <div key={t.id} style={styles.settingsRow}>
              <label style={styles.settingsLabel}>{t.label} → Google Doc</label>
              <input
                type="url"
                placeholder="https://docs.google.com/document/d/..."
                value={destinations[t.id] || ''}
                onChange={e => updateDestination(t.id, e.target.value)}
                style={styles.settingsInput}
              />
            </div>
          ))}
        </div>
      )}

      {/* Sprecher-Auswahl */}
      <div style={styles.speakerRow}>
        {SPEAKERS.map(name => (
          <button
            key={name}
            onClick={() => selectSpeaker(name)}
            disabled={isDisabled || isRecording}
            style={{
              ...styles.speakerButton,
              ...(speaker === name ? styles.speakerActive : {}),
            }}
          >
            {name}
          </button>
        ))}
      </div>

      {/* Template-Auswahl */}
      <select
        value={template}
        onChange={e => setTemplate(e.target.value)}
        disabled={isDisabled || isRecording}
        style={styles.select}
      >
        {TEMPLATES.map(t => (
          <option key={t.id} value={t.id}>{t.label}</option>
        ))}
      </select>

      {/* Großer Record-Button */}
      <button
        onClick={handleButtonClick}
        disabled={isDisabled}
        style={{
          ...styles.button,
          background: isRecording ? '#cc0000' : '#1a1a2e',
          transform:  isRecording ? 'scale(1.05)' : 'scale(1)',
        }}
      >
        {isRecording ? '■  Stop' : '●  Record'}
      </button>

      {/* Status */}
      <p style={styles.status}>{STATUS_MESSAGES[status]}</p>

      {/* Fehlermeldung */}
      {status === 'error' && (
        <p style={styles.error}>{errorMsg}</p>
      )}

      {/* Nicht gesendete Aufnahme */}
      {pending && (
        <div style={styles.pendingCard}>
          <p style={styles.pendingTitle}>Nicht gesendete Aufnahme</p>
          <p style={styles.pendingMeta}>
            {TEMPLATES.find(t => t.id === pending.template)?.label || pending.template}
            {' · '}{pending.speaker}
            {' · '}{new Date(pending.savedAt).toLocaleString('de-DE', {
              day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
            })}{' Uhr'}
          </p>
          <div style={styles.pendingButtons}>
            <button
              onClick={retryPending}
              disabled={isDisabled || isRecording}
              style={styles.pendingRetry}
            >
              Erneut senden
            </button>
            <button
              onClick={discardPending}
              disabled={isDisabled}
              style={styles.pendingDiscard}
            >
              Verwerfen
            </button>
          </div>
        </div>
      )}

      {/* Antwort vom Backend */}
      {result && (
        <div style={styles.result}>
          {result.formatted ? (
            <>
              <p style={styles.resultLabel}>{TEMPLATES.find(t => t.id === result.template)?.label}</p>
              <div style={styles.formatted}>{result.formatted}</div>
              <details style={styles.details}>
                <summary style={styles.summary}>Rohes Transkript</summary>
                <p style={styles.transcript}>{result.transcript}</p>
              </details>
            </>
          ) : (
            <>
              <p style={styles.resultLabel}>Transkript</p>
              <p style={styles.transcript}>{result.transcript}</p>
            </>
          )}
          <p style={styles.meta}>{result.template} · {result.file_size_kb} KB</p>
          {result.doc_written === true && (
            <p style={styles.docSuccess}>✓ Gespeichert in Google Doc</p>
          )}
          {result.doc_written === false && destinations[result.template] && (
            <p style={styles.docWarning}>⚠ Google Doc konnte nicht beschrieben werden</p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Styles (inline – alles an einem Ort, kein CSS-File nötig) ───────────────

const styles = {
  page: {
    display:        'flex',
    flexDirection:  'column',
    alignItems:     'center',
    justifyContent: 'center',
    minHeight:      '100vh',
    padding:        '2rem',
    background:     '#f0f4f8',
    fontFamily:     'system-ui, -apple-system, sans-serif',
    gap:            '1.5rem',
  },
  header: {
    display:    'flex',
    alignItems: 'center',
    gap:        '0.75rem',
  },
  title: {
    fontSize:   '2rem',
    fontWeight: 700,
    color:      '#1a1a2e',
    margin:     0,
  },
  gearButton: {
    background: 'none',
    border:     'none',
    fontSize:   '1.4rem',
    cursor:     'pointer',
    padding:    '0.25rem',
    color:      '#888',
    lineHeight: 1,
  },
  settingsPanel: {
    background:    '#fff',
    borderRadius:  '12px',
    padding:       '1.25rem',
    width:         '100%',
    maxWidth:      '320px',
    boxShadow:     '0 2px 10px rgba(0,0,0,0.1)',
    display:       'flex',
    flexDirection: 'column',
    gap:           '0.75rem',
  },
  settingsTitle: {
    fontSize:      '0.75rem',
    fontWeight:    700,
    textTransform: 'uppercase',
    color:         '#888',
    margin:        0,
    letterSpacing: '0.05em',
  },
  settingsRow: {
    display:       'flex',
    flexDirection: 'column',
    gap:           '0.3rem',
  },
  settingsLabel: {
    fontSize:   '0.85rem',
    color:      '#444',
    fontWeight: 600,
  },
  settingsInput: {
    fontSize:     '0.85rem',
    padding:      '0.5rem 0.75rem',
    borderRadius: '6px',
    border:       '1px solid #ccc',
    width:        '100%',
    boxSizing:    'border-box',
  },
  speakerRow: {
    display: 'flex',
    gap:     '0.5rem',
  },
  speakerButton: {
    padding:      '0.5rem 1.75rem',
    borderRadius: '999px',
    border:       '2px solid #1a1a2e',
    background:   '#fff',
    color:        '#1a1a2e',
    fontSize:     '1rem',
    fontWeight:   600,
    cursor:       'pointer',
    transition:   'all 0.15s ease',
  },
  speakerActive: {
    background: '#1a1a2e',
    color:      '#fff',
  },
  select: {
    fontSize:     '1.1rem',
    padding:      '0.75rem 1rem',
    borderRadius: '8px',
    border:       '2px solid #1a1a2e',
    width:        '100%',
    maxWidth:     '320px',
    background:   '#fff',
  },
  button: {
    width:        '180px',
    height:       '180px',
    borderRadius: '50%',
    border:       'none',
    color:        'white',
    fontSize:     '1.2rem',
    fontWeight:   700,
    cursor:       'pointer',
    transition:   'all 0.15s ease',
    boxShadow:    '0 4px 20px rgba(0,0,0,0.25)',
  },
  status: {
    fontSize: '1.1rem',
    color:    '#444',
    margin:   0,
  },
  error: {
    color:     '#cc0000',
    textAlign: 'center',
    maxWidth:  '320px',
    margin:    0,
  },
  pendingCard: {
    background:    '#fff7e8',
    border:        '1px solid #e8c88a',
    borderRadius:  '12px',
    padding:       '1rem 1.25rem',
    width:         '100%',
    maxWidth:      '320px',
    display:       'flex',
    flexDirection: 'column',
    gap:           '0.5rem',
    boxSizing:     'border-box',
  },
  pendingTitle: {
    fontSize:      '0.8rem',
    fontWeight:    700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color:         '#b07908',
    margin:        0,
  },
  pendingMeta: {
    fontSize: '0.9rem',
    color:    '#6b5834',
    margin:   0,
  },
  pendingButtons: {
    display:   'flex',
    gap:       '0.5rem',
    marginTop: '0.25rem',
  },
  pendingRetry: {
    flex:         1,
    padding:      '0.55rem 0.75rem',
    borderRadius: '8px',
    border:       'none',
    background:   '#1a1a2e',
    color:        '#fff',
    fontSize:     '0.9rem',
    fontWeight:   600,
    cursor:       'pointer',
  },
  pendingDiscard: {
    padding:      '0.55rem 0.75rem',
    borderRadius: '8px',
    border:       '1px solid #ccc',
    background:   '#fff',
    color:        '#888',
    fontSize:     '0.9rem',
    cursor:       'pointer',
  },
  result: {
    background:   '#fff',
    borderRadius: '12px',
    padding:      '1.5rem',
    width:        '100%',
    maxWidth:     '320px',
    boxShadow:    '0 2px 10px rgba(0,0,0,0.1)',
    lineHeight:   1.7,
    fontSize:     '0.95rem',
  },
  resultLabel: {
    fontSize:     '0.75rem',
    fontWeight:   700,
    textTransform: 'uppercase',
    color:        '#888',
    margin:       '0 0 0.5rem 0',
    letterSpacing: '0.05em',
  },
  formatted: {
    fontSize:   '1.05rem',
    color:      '#1a1a2e',
    margin:     '0 0 1rem 0',
    whiteSpace: 'pre-wrap',
    lineHeight: 1.8,
  },
  details: {
    marginBottom: '1rem',
  },
  summary: {
    fontSize:  '0.8rem',
    color:     '#888',
    cursor:    'pointer',
    marginBottom: '0.5rem',
  },
  transcript: {
    fontSize:   '0.9rem',
    color:      '#888',
    margin:     '0.5rem 0 0 0',
    whiteSpace: 'pre-wrap',
    lineHeight: 1.6,
  },
  meta: {
    fontSize: '0.8rem',
    color:    '#aaa',
    margin:   0,
  },
  docSuccess: {
    fontSize:   '0.8rem',
    color:      '#2a9d5c',
    margin:     '0.25rem 0 0 0',
    fontWeight: 600,
  },
  docWarning: {
    fontSize: '0.8rem',
    color:    '#e07b00',
    margin:   '0.25rem 0 0 0',
  },
}
