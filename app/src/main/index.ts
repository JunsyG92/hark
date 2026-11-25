import { app, globalShortcut, ipcMain } from 'electron'
import { join } from 'node:path'
import { forward, validateApiRequest } from './apiProxy'
import { setLaunchAtLogin } from './autostart'
import { Engine, resolveEngineCommand } from './engine'
import { SettingsStore, isValidAccelerator, type AppSettings } from './settings'
import { AppTray } from './tray'
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

  kanban.create()
  tray.create()
  registerShortcut(settings.get().shortcut)

  app.on('second-instance', () => kanban.show())
  app.on('activate', () => kanban.show())
  app.on('window-all-closed', () => {
    /* stay in tray */
  })
  app.on('before-quit', () => {
    kanban.setQuitting()
    globalShortcut.unregisterAll()
    engine.stop()
  })

  if (!process.argv.includes('--hidden') && !app.isPackaged) kanban.show()
}
