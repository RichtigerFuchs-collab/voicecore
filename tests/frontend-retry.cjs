// Browser regression with synthetic audio and intercepted API requests.
// Usage: VOICECORE_BASE_URL=http://127.0.0.1:8765 node tests/frontend-retry.cjs
const assert = require('node:assert/strict')
const { chromium } = require(process.env.VOICECORE_PLAYWRIGHT_PATH || 'playwright')

const base = process.env.VOICECORE_BASE_URL || 'http://127.0.0.1:8765'
const failure = { transcript: 'Referenz', formatted: null, markdown: null,
  error: 'Inhaltsprüfung: Ein Detail fehlt.', doc_written: false, queued_for_obsidian: false }
const success = { transcript: 'Referenz', formatted: 'Vollständiger Eintrag',
  markdown: '## Vollständiger Eintrag', doc_written: false, queued_for_obsidian: false }

async function readPending(page) {
  return page.evaluate(() => new Promise((resolve, reject) => {
    const req = indexedDB.open('voicecore', 1)
    req.onsuccess = () => {
      const get = req.result.transaction('pending', 'readonly').objectStore('pending').get('last')
      get.onsuccess = () => resolve(get.result ? {
        speaker: get.result.speaker, template: get.result.template,
        size: get.result.blob.size, processed: Boolean(get.result.processed),
      } : null)
      get.onerror = () => reject(get.error)
    }
    req.onerror = () => reject(req.error)
  }))
}

async function seedPending(page) {
  await page.evaluate(() => new Promise((resolve, reject) => {
    const req = indexedDB.open('voicecore', 1)
    req.onsuccess = () => {
      const tx = req.result.transaction('pending', 'readwrite')
      tx.objectStore('pending').put({ blob: new Blob(['synthetic audio'], { type: 'audio/webm' }),
        mimeType: 'audio/webm', template: 'tagebuch', speaker: 'Kathrin', savedAt: Date.now() }, 'last')
      tx.oncomplete = resolve
      tx.onerror = () => reject(tx.error)
    }
  }))
  await page.reload()
  await page.getByRole('button', { name: 'Erneut senden', exact: true }).waitFor()
}

async function recording(page) {
  await page.getByRole('button', { name: '● Record', exact: true }).click()
  await page.getByRole('button', { name: '■ Stop', exact: true }).waitFor()
  await page.getByRole('button', { name: '■ Stop', exact: true }).click()
}

async function ready(context) {
  const page = await context.newPage()
  await page.goto(base)
  await page.waitForFunction(() => {
    const record = [...document.querySelectorAll('button')].find(b => b.textContent.replace(/\s+/g, ' ').trim() === '● Record')
    return record && !record.disabled
  })
  return page
}

async function main() {
  const browser = await chromium.launch({ headless: true,
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })
  let count = 0
  async function scenario(name, test) {
    const context = await browser.newContext({ serviceWorkers: 'block', permissions: ['microphone'] })
    let handleUpload = async route => route.fulfill({ json: failure })
    await context.route('**/*', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/health') return route.fulfill({ json: { status: 'ok' } })
      if (url.pathname === '/upload') return handleUpload(route)
      if (url.origin === new URL(base).origin) return route.continue()
      return route.abort() // Never contact the production API.
    })
    try {
      await test(context, handler => { handleUpload = handler })
      count++
      console.log(`PASS ${name}`)
    } finally { await context.close() }
  }
  try {
    await scenario('save before HTTP; visible audit error; reload; original speaker/template on retry',
      async (context, setUpload) => {
        const page = await ready(context)
        let requests = 0
        setUpload(async route => {
          requests++
          const pending = await readPending(page)
          assert.ok(pending && pending.size > 0, 'Audio persisted before upload')
          return route.fulfill({ json: failure })
        })
        await page.getByRole('button', { name: 'Kathrin', exact: true }).click()
        await recording(page)
        await page.getByText(/Inhaltsprüfung: Ein Detail fehlt/).waitFor()
        assert.equal(requests, 1)
        assert.equal(await page.getByRole('button', { name: '● Record', exact: true }).isDisabled(), true)
        await page.reload()
        await page.getByRole('button', { name: 'Erneut senden', exact: true }).waitFor()
        await page.getByRole('button', { name: 'Kim', exact: true }).click()
        await page.locator('select').selectOption('quick_note')
        setUpload(async route => {
          requests++
          const data = route.request().postDataBuffer().toString()
          assert.match(data, /name="speaker"\r\n\r\nKathrin/)
          assert.match(data, /name="template"\r\n\r\ntagebuch/)
          return route.fulfill({ json: success })
        })
        await page.getByRole('button', { name: 'Erneut senden', exact: true }).click()
        await page.getByText('Vollständiger Eintrag', { exact: true }).waitFor()
        assert.equal(requests, 2)
        assert.equal(await readPending(page), null)
      })

    await scenario('reload during an outstanding request retains audio and prevents overwriting',
      async (context, setUpload) => {
        const page = await ready(context)
        let requestStarted = false
        setUpload(async route => {
          requestStarted = true
          await new Promise(resolve => setTimeout(resolve, 2000))
          await route.fulfill({ json: failure }).catch(() => {})
        })
        await recording(page)
        for (let i = 0; i < 100 && !requestStarted; i++) await new Promise(resolve => setTimeout(resolve, 10))
        assert.equal(requestStarted, true)
        await page.reload()
        await page.getByRole('button', { name: 'Erneut senden', exact: true }).waitFor()
        assert.ok((await readPending(page)).size > 0)
        assert.equal(await page.getByRole('button', { name: '● Record', exact: true }).isDisabled(), true)
      })

    await scenario('storage failure does not upload or claim a durable backup',
      async (context, setUpload) => {
        const page = await ready(context)
        let requests = 0
        setUpload(async route => { requests++; await route.fulfill({ json: success }) })
        await page.evaluate(() => {
          IDBObjectStore.prototype.put = function () { throw new Error('synthetic storage failure') }
        })
        await recording(page)
        await page.getByText(/nicht dauerhaft gespeichert/).waitFor()
        assert.equal(requests, 0)
        assert.equal(await readPending(page), null)
        assert.equal(await page.getByRole('button', { name: '● Record', exact: true }).isDisabled(), true)
      })

    await scenario('local deletion failure after success offers local cleanup, including after reload',
      async (context, setUpload) => {
        const page = await ready(context)
        await seedPending(page)
        let requests = 0
        setUpload(async route => { requests++; await route.fulfill({ json: success }) })
        await page.evaluate(() => {
          IDBObjectStore.prototype.delete = function () { throw new Error('synthetic delete failure') }
        })
        await page.getByRole('button', { name: 'Erneut senden', exact: true }).click()
        await page.getByText(/Der Eintrag wurde verarbeitet/).waitFor()
        assert.equal(requests, 1)
        assert.equal((await readPending(page)).processed, true)
        await page.reload()
        await page.getByRole('button', { name: 'Lokal entfernen', exact: true }).waitFor()
        await page.getByRole('button', { name: 'Lokal entfernen', exact: true }).click()
        await page.waitForFunction(() => !document.body.textContent.includes('lokale Sicherung'))
        assert.equal(requests, 1)
        assert.equal(await readPending(page), null)
      })

    await scenario('pending-load failure prevents new recording and slot overwriting', async context => {
      await context.addInitScript(() => {
        const original = IDBObjectStore.prototype.get
        IDBObjectStore.prototype.get = function (key) {
          if (this.name === 'pending') throw new Error('synthetic read failure')
          return original.call(this, key)
        }
      })
      const page = await context.newPage()
      await page.goto(base)
      await page.getByText(/Gespeicherte Aufnahmen konnten nicht geladen werden/).waitFor()
      assert.equal(await page.getByRole('button', { name: '● Record', exact: true }).isDisabled(), true)
    })
    await scenario('a valid transcript beginning with a bracket is accepted', async (context, setUpload) => {
      const page = await ready(context)
      await seedPending(page)
      setUpload(async route => route.fulfill({ json: { ...success, transcript: '[unverständlich] Heute am Rhein.' } }))
      await page.getByRole('button', { name: 'Erneut senden', exact: true }).click()
      await page.getByText('Vollständiger Eintrag', { exact: true }).waitFor()
      assert.equal(await readPending(page), null)
    })
    console.log(`${count} browser scenarios passed; all uploads and health requests intercepted.`)
  } finally { await browser.close() }
}

main().catch(err => { console.error(err); process.exitCode = 1 })
