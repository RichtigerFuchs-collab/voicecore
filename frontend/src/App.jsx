import { useState, useRef } from 'react'

// ─── Konstanten ───────────────────────────────────────────────────────────────

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TEMPLATES = [
  { id: 'tagebuch',          label: 'Tagebuch' },
  { id: 'quick_note',        label: 'Quick Note' },
  { id: 'restaurant_review', label: 'Restaurant Review' },
]

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

  // Refs für Werte die kein Re-Render auslösen sollen
  const mediaRecorderRef = useRef(null)
  const audioChunksRef   = useRef([])

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

  async function uploadAudio(chunks, mimeType) {
    const audioBlob = new Blob(chunks, { type: mimeType || 'audio/webm' })

    const ext      = mimeType?.includes('mp4') ? 'm4a'
                   : mimeType?.includes('ogg') ? 'ogg'
                   : 'webm'

    const formData = new FormData()
    formData.append('audio', audioBlob, `recording.${ext}`)
    formData.append('template', template)

    try {
      const response = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        body: formData,
        // Content-Type NICHT manuell setzen — Browser setzt den multipart-Boundary
      })

      if (!response.ok) throw new Error(`Server-Fehler: ${response.status}`)

      const data = await response.json()
      setResult(data)
      setStatus('done')

    } catch (err) {
      setErrorMsg(err.message)
      setStatus('error')
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  const isRecording = status === 'recording'
  const isDisabled  = status === 'uploading'

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>VoiceCore</h1>

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

      {/* Antwort vom Backend */}
      {result && (
        <div style={styles.result}>
          <p><strong>Job ID:</strong> {result.job_id}</p>
          <p><strong>Template:</strong> {result.template}</p>
          <p><strong>Dateigröße:</strong> {result.file_size_kb} KB</p>
          <p style={{ color: '#006644' }}>{result.stub_response}</p>
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
  title: {
    fontSize:   '2rem',
    fontWeight: 700,
    color:      '#1a1a2e',
    margin:     0,
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
}
