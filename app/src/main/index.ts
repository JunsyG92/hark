import { Notification, app, globalShortcut, ipcMain } from 'electron'
import { join } from 'node:path'
import { forward, validateApiRequest } from './apiProxy'
import { setLaunchAtLogin } from './autostart'
import { parseDetected, parseToastResponse } from './detection'
import { Engine, resolveEngineCommand } from './engine'
import { EngineEvents } from './events'
import { SettingsStore, isValidAccelerator, type AppSettings } from './settings'
import { AppTray } from './tray'
import { ToastWindow } from './toast'
import { KanbanWindow } from './window'

const log = (msg: string): void => console.log(`[hark] ${msg}`)

app.setName('Hark')
if (process.platform === 'linux') {
  // Global shortcuts on Wayland go through the XDG desktop portal.
  app.commandLine.appendSwitch('enable-features', 'GlobalShortcutsPortal')
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  void main()
}

async function main(): Promise<void> {
  await app.whenReady()
  const settings = new SettingsStore(join(app.getPath('userData'), 'settings.json'))
  const kanban = new KanbanWindow(log)
  const toast = new ToastWindow()
  const engine = new Engine(
    resolveEngineCommand({
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      appPath: app.getAppPath(),
      env: process.env,
      platform: process.platform,
    }),
    log,
  )
  engine.start()

  const tray = new AppTray(
    {
      openKanban: () => kanban.show(),
      toggleLaunchAtLogin: (enabled) => applySettings({ launchAtLogin: enabled }),
      quit: () => app.quit(),
    },
    () => settings.get(),
  )

  function registerShortcut(accelerator: string): boolean {
    globalShortcut.unregisterAll()
    const ok = globalShortcut.register(accelerator, () => kanban.toggle())
    if (!ok) log(`could not register global shortcut ${accelerator} (already used?)`)
    return ok
  }

  function applySettings(patch: Partial<AppSettings>): AppSettings {
    const before = settings.get()
    if (patch.shortcut !== undefined && !isValidAccelerator(patch.shortcut)) {
      throw new Error('raccourci invalide')
    }
    if (patch.shortcut && patch.shortcut !== before.shortcut && !registerShortcut(patch.shortcut)) {
      registerShortcut(before.shortcut)
      throw new Error('raccourci déjà utilisé par une autre application')
    }
    const next = settings.update(patch)
    if (next.launchAtLogin !== before.launchAtLogin) setLaunchAtLogin(next.launchAtLogin)
    tray.refreshMenu()
    return next
  }

  ipcMain.handle('hark:api', async (_e, raw: unknown) => {
    const req = validateApiRequest(raw)
    return forward(req, await engine.ready())
  })
  ipcMain.handle('hark:settings:get', () => settings.get())
  ipcMain.handle('hark:settings:set', (_e, patch: unknown) =>
    applySettings((patch && typeof patch === 'object' ? patch : {}) as Partial<AppSettings>),
  )
  ipcMain.on('hark:hide', () => kanban.hide())

  ipcMain.on('hark:toast:respond', (e, raw: unknown) => {
    if (e.sender !== toast.webContents) return // only our toast window may answer
    const answer = parseToastResponse(raw)
    toast.hide()
    if (!answer) return
    void (async () => {
      try {
        const res = await forward(
          { method: 'POST', path: '/v1/detection/respond', body: { prompt_id: answer.promptId, action: answer.action } },
          await engine.ready(),
        )
        const body = res.body as { ok?: boolean; recording_started?: boolean } | null
        if (answer.action === 'record' && body?.ok && !body.recording_started) {
          new Notification({
            title: 'Hark',
            body: "L'enregistrement n'est pas encore disponible dans cette version (étape 3). Rien n'a été enregistré.",
          }).show()
        }
      } catch (err) {
        log(`could not send toast answer: ${(err as Error).message}`)
      }
    })()
  })

  const events = new EngineEvents(
    () => engine.ready(),
    (ev) => {
      if (ev.type === 'meeting.detected') {
        const prompt = parseDetected(ev.data)
        if (prompt) toast.show(prompt)
      } else if (ev.type.startsWith('task.')) {
        kanban.webContents?.send('hark:tasks-changed')
      }
    },
    log,
  )

  kanban.create()
  toast.create()
  events.start()
  tray.create()
  registerShortcut(settings.get().shortcut)

  app.on('second-instance', () => kanban.show())
  app.on('activate', () => kanban.show())
  app.on('window-all-closed', () => {
    /* stay in tray */
  })
  app.on('before-quit', () => {
    kanban.setQuitting()
    events.stop()
    toast.destroy()
    globalShortcut.unregisterAll()
    engine.stop()
  })

  if (!process.argv.includes('--hidden') && !app.isPackaged) kanban.show()
}
