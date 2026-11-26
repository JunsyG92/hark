// Smoke test of the real desktop app (Electron + engine sidecar).
// Run: pnpm build && pnpm e2e   (Linux CI: xvfb-run -a pnpm e2e)
const { _electron: electron } = require('playwright-core')
const { existsSync, mkdtempSync, statSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join, resolve } = require('node:path')
const electronPath = require('electron')
const appDir = resolve(__dirname, '..')
const outDir = mkdtempSync(join(tmpdir(), 'hark-e2e-'))
const dataDir = join(outDir, 'data')
// The hidden consent toast is also a window: always pick the kanban explicitly.
async function kanbanWindow(app) {
  for (let i = 0; i < 100; i++) {
    const w = app.windows().find((x) => x.url().includes('index.html') || (x.url().startsWith('http') && !x.url().includes('toast')))
    if (w) return w
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('kanban window not found')
}
const sandboxArgs = process.getuid && process.getuid() === 0 ? ['--no-sandbox'] : []
;(async () => {
  const app = await electron.launch({
    executablePath: electronPath,
    args: [...sandboxArgs, appDir],
    env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0', HARK_FAKE_AUDIO: '1', HARK_FAKE_STT: '1', HARK_FAKE_LLM: '1' },
  })
  const logs = []
  app.process().stdout.on('data', (d) => logs.push(String(d)))
  app.process().stderr.on('data', (d) => logs.push(String(d)))
  const win = await kanbanWindow(app)
  await win.setViewportSize({ width: 1180, height: 720 })
  await win.waitForSelector('[data-quick-add="todo"]')
  for (const t of ['Préparer la démo client', 'Relire le contrat']) {
    await win.fill('[data-quick-add="todo"]', t)
    await win.press('[data-quick-add="todo"]', 'Enter')
    await win.waitForSelector(`text=${t}`)
  }
  await win.fill('[data-quick-add="in_progress"]', 'Corriger le bug d’export')
  await win.press('[data-quick-add="in_progress"]', 'Enter')
  await win.waitForSelector('text=Corriger le bug')
  // drag first todo card to Done column
  const card = win.locator('[data-testid=task-card]', { hasText: 'Relire le contrat' })
  const done = win.locator('[data-column=done] .column__list')
  const cb = await card.boundingBox(), db = await done.boundingBox()
  await win.mouse.move(cb.x + 20, cb.y + 10); await win.mouse.down()
  await win.mouse.move(cb.x + 40, cb.y + 20, { steps: 5 })
  await win.mouse.move(db.x + 40, db.y + 20, { steps: 15 }); await win.mouse.up()
  await win.waitForTimeout(500)
  // toggle timing: hide then show via main
  const timings = await app.evaluate(async ({ BrowserWindow }) => {
    const w = BrowserWindow.getAllWindows().find((x) => x.webContents.getURL().includes('index.html')); const out = []
    for (let i = 0; i < 5; i++) { w.hide(); const t = performance.now(); w.show(); w.focus(); out.push(performance.now() - t) }
    return out
  })
  // --- consent toast (step 2): a test detection must show the toast; "Non" must start the cooldown
  const call = (method, path, body) => win.evaluate((r) => window.hark.api(r), { method, path, body })
  const prompted = await call('POST', '/v1/detection/test')
  if (!prompted.body.prompted) throw new Error('test prompt refused')
  const toastWin = await (async () => {
    for (let i = 0; i < 50; i++) {
      const w = app.windows().find((x) => x.url().includes('toast.html'))
      if (w) return w
      await new Promise((r) => setTimeout(r, 100))
    }
    throw new Error('toast window not found')
  })()
  await toastWin.waitForSelector('#b-primary:visible')
  const toastText = await toastWin.locator('#toast').innerText()
  if (!toastText.includes('Pense à informer les participants')) throw new Error('consent reminder missing')
  const visible = await app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().some((w) => w.webContents.getURL().includes('toast.html') && w.isVisible()))
  if (!visible) throw new Error('toast not visible')
  let status = (await call('GET', '/v1/detection/status')).body
  if (status.phase !== 'prompted') throw new Error('expected prompted, got ' + status.phase)
  await toastWin.click('#b-secondary')
  await new Promise((r) => setTimeout(r, 500))
  status = (await call('GET', '/v1/detection/status')).body
  if (status.phase !== 'cooldown') throw new Error('expected cooldown after "Non", got ' + status.phase)
  const hidden = await app.evaluate(({ BrowserWindow }) =>
    !BrowserWindow.getAllWindows().some((w) => w.webContents.getURL().includes('toast.html') && w.isVisible()))
  if (!hidden) throw new Error('toast still visible after answer')
  // --- team follow-up: assign a task to a person (first name, last name, e-mail) and filter by person
  const inès = (await call('POST', '/v1/people', { first_name: 'Inès', last_name: 'Roy', email: 'ines@example.com' })).body
  await win.locator('[data-testid=task-card]', { hasText: 'Préparer la démo client' }).click()
  await win.selectOption('select[aria-label="Assigné à"]', inès.id)
  await win.click('.modal button[type=submit]')
  await win.waitForSelector('[data-testid=task-card]:has-text("Préparer la démo client") .avatar:has-text("IR")')
  await win.selectOption('select[aria-label="Filtrer les tâches"]', 'person:' + inès.id)
  const filtered = await win.locator('[data-testid=task-card]').allTextContents()
  if (filtered.length !== 1 || !filtered[0].includes('Préparer la démo client')) throw new Error('person filter failed: ' + JSON.stringify(filtered))
  await win.selectOption('select[aria-label="Filtrer les tâches"]', 'all')
  const assignedTask = (await call('GET', '/v1/tasks?assignee_id=' + inès.id)).body
  if (assignedTask.length !== 1 || assignedTask[0].assignee !== 'Inès Roy') throw new Error('assignment not saved')
  // --- recording (step 3) with synthetic audio: explicit click, overlay, title, stop, FLAC files
  const overlayWin = () => app.windows().find((x) => x.url().includes('overlay.html'))
  const overlayVisible = () => app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().some((w) => w.webContents.getURL().includes('overlay.html') && w.isVisible()))
  if ((await call('GET', '/v1/recording/status')).body.recording) throw new Error('recording without any click')
  if (await overlayVisible()) throw new Error('overlay visible before recording: ' + JSON.stringify(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().map((w) => [w.webContents.getURL().split('/').pop(), w.isVisible()]))))
  await call('PATCH', '/v1/settings/transcription', { auto_transcribe: false, retention_days: 7 })
  await win.click('[data-testid=rec-button]')
  await win.waitForSelector('text=REC')
  for (let i = 0; i < 50 && !(await overlayVisible()); i++) await new Promise((r) => setTimeout(r, 100))
  if (!(await overlayVisible())) throw new Error('recording overlay not visible')
  const ov = overlayWin()
  await ov.fill('#o-title', 'Revue budget Q1')
  await ov.press('#o-title', 'Enter')
  await new Promise((r) => setTimeout(r, 2800))
  let rec = (await call('GET', '/v1/recording/status')).body
  if (!rec.recording || rec.tracks.length !== 2) throw new Error('expected 2 tracks, got ' + JSON.stringify(rec))
  if (rec.system_level_db === null || rec.system_level_db < -40) throw new Error('system level missing')
  if (rec.title !== 'Revue budget Q1') throw new Error('title from overlay not saved: ' + rec.title)
  await ov.click('#o-stop')
  for (let i = 0; i < 50 && (await overlayVisible()); i++) await new Promise((r) => setTimeout(r, 100))
  if (await overlayVisible()) throw new Error('overlay still visible after stop')
  const list = (await call('GET', '/v1/meetings')).body
  const m = list[0]
  if (list.length !== 1 || m.status !== 'recorded' || m.duration_ms < 2000 || !m.audio_available) throw new Error('bad meeting ' + JSON.stringify(list))
  for (const kind of ['system', 'mic']) {
    const f = join(dataDir, 'audio', m.id, kind + '.wav')
    if (!existsSync(f) || statSync(f).size < 1000) throw new Error('missing/empty ' + f)
  }
  console.log('recorded:', m.title, m.duration_ms, 'ms')
  if (m.transcription !== 'none') throw new Error('transcribed although auto_transcribe is off')
  // --- transcription (step 4, synthetic STT): queue, segments, search, export, retention
  const waitDone = async (id) => {
    for (let i = 0; i < 100; i++) {
      const cur = (await call('GET', '/v1/meetings/' + id)).body
      if (cur.transcription === 'done') return cur
      await new Promise((r) => setTimeout(r, 100))
    }
    throw new Error('transcription did not finish')
  }
  await call('POST', '/v1/meetings/' + m.id + '/transcribe')
  const finished = await waitDone(m.id)
  if (finished.language !== 'fr' || !finished.audio_available) throw new Error('retention 7 days must keep the audio: ' + JSON.stringify(finished))
  const segs = (await call('GET', '/v1/meetings/' + m.id + '/transcript')).body
  if (segs.map((x) => x.speaker).join() !== 'others,me') throw new Error('bad speakers ' + JSON.stringify(segs))
  const hits = (await call('GET', '/v1/search?q=budget')).body
  if (!hits.length || !hits.some((h) => h.snippet.includes('<mark>'))) throw new Error('search failed ' + JSON.stringify(hits))
  const md = (await call('GET', '/v1/meetings/' + m.id + '/export.md')).body
  if (!String(md).includes('# Revue budget Q1') || !String(md).includes('Moi')) throw new Error('bad export')
  await win.click('button.tab:has-text("Réunions")')
  await win.click('.meeting-row:has-text("Revue budget Q1")')
  await win.waitForSelector('.transcript__row:has-text("Bonjour à tous")')
  await win.fill('.meetings__search', 'budget')
  await win.waitForSelector('mark')
  await win.screenshot({ path: join(outDir, 'meetings.png') })
  await win.fill('.meetings__search', '')
  await win.click('button.tab:has-text("Kanban")')
  // --- analysis (step 5, synthetic LLM): automatic after the transcript, tasks only in « À valider »
  const waitAnalysis = async (id) => {
    for (let i = 0; i < 100; i++) {
      const cur = (await call('GET', '/v1/meetings/' + id)).body
      if (cur.analysis === 'done') return cur
      await new Promise((r) => setTimeout(r, 100))
    }
    throw new Error('analysis did not finish')
  }
  await waitAnalysis(m.id)
  const proposed = (await call('GET', '/v1/tasks?column=to_validate')).body
  if (proposed.length !== 2 || proposed.some((t) => t.source !== 'meeting:' + m.id)) throw new Error('bad proposals ' + JSON.stringify(proposed))
  if ((await call('GET', '/v1/tasks?column=todo')).body.some((t) => t.source.startsWith('meeting:'))) throw new Error('AI task outside À valider')
  const mine = proposed.filter((t) => t.is_mine)
  if (mine.length !== 1 || !mine[0].title.startsWith('Envoyer le budget') || mine[0].evidence.start_ms !== 4000) throw new Error('mine flag wrong ' + JSON.stringify(proposed))
  const an = (await call('GET', '/v1/meetings/' + m.id + '/analysis')).body
  if (!an.summary.includes('réserve') || an.tokens_in <= 0 || an.tasks_proposed !== 2) throw new Error('bad analysis ' + JSON.stringify(an))
  if (!(await call('GET', '/v1/search?q=reserve')).body.some((h) => h.kind === 'summary')) throw new Error('summary not searchable')
  // cache: asking again for the same input must not run the LLM again
  await call('POST', '/v1/meetings/' + m.id + '/analyze')
  await new Promise((r) => setTimeout(r, 800))
  const again = (await call('GET', '/v1/meetings/' + m.id + '/analysis')).body
  if (again.created_at !== an.created_at) throw new Error('analysis was recomputed for identical input')
  // UI: mine first in the column, link from the task to the source excerpt
  await win.waitForSelector('[data-column=to_validate] [data-testid=task-card]')
  const firstCard = win.locator('[data-column=to_validate] [data-testid=task-card]').first()
  if (!(await firstCard.getAttribute('class')).includes('card--mine')) throw new Error('my task is not first in À valider')
  await firstCard.click()
  await win.click('button:has-text("voir l’extrait")')
  await win.waitForSelector('.transcript__row--focus:has-text("budget")')
  await win.waitForSelector('text=Le budget est validé avec une réserve')
  await win.screenshot({ path: join(outDir, 'analysis.png') })
  await win.click('button.tab:has-text("Kanban")')
  // default retention: audio removed right after a successful transcription, transcript kept
  await call('PATCH', '/v1/settings/transcription', { retention_days: 0 })
  await call('POST', '/v1/meetings/' + m.id + '/transcribe').catch(() => undefined)
  for (let i = 0; i < 50; i++) {
    const cur = (await call('GET', '/v1/meetings/' + m.id)).body
    if (!cur.audio_available) break
    await new Promise((r) => setTimeout(r, 100))
  }
  const after = (await call('GET', '/v1/meetings/' + m.id)).body
  if (after.audio_available) throw new Error('audio not deleted after transcription with retention 0')
  if (existsSync(join(dataDir, 'audio', m.id, 'system.wav'))) throw new Error('audio file still on disk')
  if ((await call('GET', '/v1/meetings/' + m.id + '/transcript')).body.length !== 2) throw new Error('transcript lost')
  // second recording, left running: quitting the app must finalize it (no corrupted file)
  await call('POST', '/v1/recording/start', { title: 'Interrompue' })
  await new Promise((r) => setTimeout(r, 1500))
  await win.screenshot({ path: join(outDir, 'kanban.png') })
  const doneTitles = await win.locator('[data-column=done] [data-testid=task-card]').allTextContents()
  console.log(JSON.stringify({ timings, doneTitles, screenshot: join(outDir, 'kanban.png') }))
  if (Math.max(...timings) > 300) throw new Error('kanban show took > 300 ms')
  if (doneTitles.join() !== 'Relire le contrat') throw new Error('drag and drop failed')
  await app.close()
  // restart to verify persistence
  const app2 = await electron.launch({ executablePath: electronPath, args: [...sandboxArgs, appDir], env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0', HARK_FAKE_AUDIO: '1', HARK_FAKE_STT: '1', HARK_FAKE_LLM: '1' } })
  const w2 = await kanbanWindow(app2); await w2.waitForSelector('text=Relire le contrat')
  const persisted = await w2.locator('[data-testid=task-card]').count()
  console.log('persisted:', persisted)
  const call2 = (method, path, body) => w2.evaluate((r) => window.hark.api(r), { method, path, body })
  const meetings = (await call2('GET', '/v1/meetings')).body
  if (meetings.length !== 2 || meetings.some((x) => x.status !== 'recorded')) throw new Error('quit during recording lost data: ' + JSON.stringify(meetings))
  const interrupted = meetings.find((x) => x.title === 'Interrompue')
  if (!interrupted || interrupted.duration_ms < 1000) throw new Error('interrupted recording not finalized')
  if ((await call2('GET', '/v1/recording/status')).body.recording) throw new Error('recording resumed by itself after restart')
  console.log('finalized on quit:', interrupted.duration_ms, 'ms')
  if (persisted !== 5) throw new Error('tasks not persisted: ' + persisted)
  await app2.close()
  console.log(logs.join('').split('\n').filter(l => l.includes('[hark]')).join('\n'))
})().catch((e) => { console.error(e); process.exit(1) })
