// Smoke test of the real desktop app (Electron + engine sidecar).
// Run: pnpm build && pnpm e2e   (Linux CI: xvfb-run -a pnpm e2e)
const { _electron: electron } = require('playwright-core')
const { mkdtempSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join, resolve } = require('node:path')
const electronPath = require('electron')
const appDir = resolve(__dirname, '..')
const outDir = mkdtempSync(join(tmpdir(), 'hark-e2e-'))
const dataDir = join(outDir, 'data')
const sandboxArgs = process.getuid && process.getuid() === 0 ? ['--no-sandbox'] : []
;(async () => {
  const app = await electron.launch({
    executablePath: electronPath,
    args: [...sandboxArgs, appDir],
    env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0' },
  })
  const logs = []
  app.process().stdout.on('data', (d) => logs.push(String(d)))
  app.process().stderr.on('data', (d) => logs.push(String(d)))
  const win = await app.firstWindow()
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
    const w = BrowserWindow.getAllWindows()[0]; const out = []
    for (let i = 0; i < 5; i++) { w.hide(); const t = performance.now(); w.show(); w.focus(); out.push(performance.now() - t) }
    return out
  })
  await win.screenshot({ path: join(outDir, 'kanban.png') })
  const doneTitles = await win.locator('[data-column=done] [data-testid=task-card]').allTextContents()
  console.log(JSON.stringify({ timings, doneTitles, screenshot: join(outDir, 'kanban.png') }))
  if (Math.max(...timings) > 300) throw new Error('kanban show took > 300 ms')
  if (doneTitles.join() !== 'Relire le contrat') throw new Error('drag and drop failed')
  await app.close()
  // restart to verify persistence
  const app2 = await electron.launch({ executablePath: electronPath, args: [...sandboxArgs, appDir], env: { ...process.env, HARK_DATA_DIR: dataDir, HARK_PORT: '0' } })
  const w2 = await app2.firstWindow(); await w2.waitForSelector('text=Relire le contrat')
  const persisted = await w2.locator('[data-testid=task-card]').count()
  console.log('persisted:', persisted)
  if (persisted !== 3) throw new Error('tasks not persisted')
  await app2.close()
  console.log(logs.join('').split('\n').filter(l => l.includes('[hark]')).join('\n'))
})().catch((e) => { console.error(e); process.exit(1) })
