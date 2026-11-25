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
    env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0', HARK_FAKE_AUDIO: '1' },
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
  // --- recording (step 3) with synthetic audio: explicit click, overlay, title, stop, FLAC files
  const overlayWin = () => app.windows().find((x) => x.url().includes('overlay.html'))
  const overlayVisible = () => app.evaluate(({ BrowserWindow }) =>
    BrowserWindow.getAllWindows().some((w) => w.webContents.getURL().includes('overlay.html') && w.isVisible()))
  if ((await call('GET', '/v1/recording/status')).body.recording) throw new Error('recording without any click')
  if (await overlayVisible()) throw new Error('overlay visible before recording: ' + JSON.stringify(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().map((w) => [w.webContents.getURL().split('/').pop(), w.isVisible()]))))
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
  const app2 = await electron.launch({ executablePath: electronPath, args: [...sandboxArgs, appDir], env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0', HARK_FAKE_AUDIO: '1' } })
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
  if (persisted !== 3) throw new Error('tasks not persisted')
  await app2.close()
  console.log(logs.join('').split('\n').filter(l => l.includes('[hark]')).join('\n'))
})().catch((e) => { console.error(e); process.exit(1) })
