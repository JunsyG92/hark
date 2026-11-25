import { Notification, app, dialog, globalShortcut, ipcMain } from 'electron'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { forward, validateApiRequest } from './apiProxy'
import { setLaunchAtLogin } from './autostart'
import {
  allowedActions,
  endedPayload,
  parseDetected,
  parseRecordingStarted,
  parseSilence,
  parseTitle,
  parseToastResponse,
} from './detection'
import { Engine, resolveEngineCommand } from './engine'
import { EngineEvents } from './events'
import { parseSaveRequest } from './files'
import { OverlayWindow } from './overlay'
import { SettingsStore, isValidAccelerator, type AppSettings } from './settings'
import { ToastWindow } from './toast'
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
  const toast = new ToastWindow()
  const overlay = new OverlayWindow()
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

  const call = async (method: 'GET' | 'POST' | 'PATCH' | 'PUT', path: string, body?: unknown) =>
    forward({ method, path, body }, await engine.ready())

  const notify = (body: string): void => {
    new Notification({ title: 'Hark', body }).show()
  }

  async function startRecording(): Promise<void> {
    const res = await call('POST', '/v1/recording/start', { title: '' })
    if (res.status >= 400) {
      const detail = (res.body as { detail?: string } | null)?.detail ?? `HTTP ${res.status}`
      notify(`Impossible de démarrer l'enregistrement : ${detail}`)
    } else {
      notify('Enregistrement démarré. Pense à informer les participants.')
    }
  }

  async function stopRecording(): Promise<void> {
    const res = await call('POST', '/v1/recording/stop')
    if (res.status >= 400 && res.status !== 409) notify("Impossible d'arrêter l'enregistrement.")
  }

  const tray = new AppTray(
    {
      openKanban: () => kanban.show(),
      startRecording: () => void startRecording(),
      stopRecording: () => void stopRecording(),
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
  ipcMain.handle('hark:save-file', async (e, raw: unknown) => {
    if (e.sender !== kanban.webContents) throw new Error('forbidden')
    const req = parseSaveRequest(raw)
    if (!req) throw new Error('invalid request')
    const win = kanban.window
    const options = { defaultPath: join(app.getPath('documents'), req.fileName), filters: [{ name: 'Markdown', extensions: ['md'] }] }
    const res = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options)
    if (res.canceled || !res.filePath) return { saved: false }
    await writeFile(res.filePath, req.content, 'utf8')
    return { saved: true }
  })

  // ---- consent / "meeting ended?" toast answers ---------------------------------------
  ipcMain.on('hark:toast:respond', (e, raw: unknown) => {
    if (e.sender !== toast.webContents) return // only our toast window may answer
    const answer = parseToastResponse(raw)
    const shown = toast.shown
    toast.hide()
    // Ignore stale/foreign answers: must match the prompt on screen and its kind.
    if (!answer || !shown || answer.promptId !== shown.promptId) return
    if (!allowedActions(shown.kind).includes(answer.action)) return
    void (async () => {
      try {
        if (answer.action === 'stop') return void (await stopRecording())
        if (answer.action === 'continue') return
        const res = await call('POST', '/v1/detection/respond', { prompt_id: answer.promptId, action: answer.action })
        const body = res.body as { ok?: boolean; recording_started?: boolean; error?: string | null } | null
        if (answer.action === 'record' && body?.ok && !body.recording_started) {
          notify(`L'enregistrement n'a pas pu démarrer${body.error ? ` (${body.error})` : ''}. Rien n'a été enregistré.`)
        }
      } catch (err) {
        log(`could not send toast answer: ${(err as Error).message}`)
      }
    })()
  })

  // ---- recording overlay ----------------------------------------------------------------
  ipcMain.on('hark:overlay:stop', (e) => {
    if (e.sender === overlay.webContents) void stopRecording()
  })
  ipcMain.on('hark:overlay:title', (e, raw: unknown) => {
    if (e.sender !== overlay.webContents) return
    const title = parseTitle(raw)
    const rec = overlay.recording // the meeting id comes from main's own state, never the renderer
    if (title === null || !rec) return
    void call('PATCH', `/v1/meetings/${encodeURIComponent(rec.meetingId)}`, { title })
  })

  // ---- engine events ------------------------------------------------------------------------
  const events = new EngineEvents(
    () => engine.ready(),
    (ev) => {
      if (ev.type === 'meeting.detected') {
        const prompt = parseDetected(ev.data)
        if (prompt) {
          toast.show(prompt)
          // Backup for desktops where an always-on-top window can be hidden or missed.
          if (Notification.isSupported()) {
            const n = new Notification({
              title: 'Hark — réunion détectée',
              body: `${prompt.app && prompt.app !== 'test' ? `${prompt.app} · ` : ''}Enregistrer ? ${prompt.reminder} Clique ici pour répondre.`,
            })
            n.on('click', () => toast.raise())
            n.show()
          }
        }
      } else if (ev.type === 'meeting.recording_started') {
        const info = parseRecordingStarted(ev.data)
        toast.hide()
        tray.setState('recording')
        if (info) overlay.show(info)
        kanban.webContents?.send('hark:recording-changed')
        kanban.webContents?.send('hark:meetings-changed')
      } else if (ev.type === 'meeting.recorded') {
        overlay.hide()
        toast.hideIfKind('ended')
        tray.setState('idle')
        kanban.webContents?.send('hark:recording-changed')
        kanban.webContents?.send('hark:meetings-changed')
      } else if (ev.type === 'analysis.ready') {
        kanban.webContents?.send('hark:meetings-changed')
        const n = Number(ev.data.tasks ?? 0)
        notify(n > 0 ? `Analyse terminée : ${n} tâche${n > 1 ? 's' : ''} à valider dans le kanban.` : 'Analyse terminée : résumé disponible dans Réunions.')
      } else if (ev.type === 'transcript.ready') {
        kanban.webContents?.send('hark:meetings-changed')
        notify('Transcription terminée. Retrouve-la dans l’onglet Réunions.')
      } else if (ev.type === 'meeting.silence') {
        const s = parseSilence(ev.data)
        if (!s) return
        if (s.silent) toast.show(endedPayload(s))
        else toast.hideIfKind('ended') // a voice is back: the question disappears by itself
      } else if (ev.type.startsWith('task.')) {
        kanban.webContents?.send('hark:tasks-changed')
      }
    },
    log,
  )

  kanban.create()
  toast.create()
  overlay.create()
  events.start()
  tray.create()
  registerShortcut(settings.get().shortcut)

  app.on('second-instance', () => kanban.show())
  app.on('activate', () => kanban.show())
  app.on('window-all-closed', () => {
    /* stay in tray */
  })

  // Quit: let the engine finalize an in-progress recording (FLAC files) before the process exits.
  let quitting = false
  app.on('before-quit', (e) => {
    if (quitting) return
    quitting = true
    e.preventDefault()
    kanban.setQuitting()
    events.stop()
    globalShortcut.unregisterAll()
    void engine.stop().finally(() => {
      toast.destroy()
      overlay.destroy()
      app.exit(0)
    })
  })

  if (!process.argv.includes('--hidden') && !app.isPackaged) kanban.show()
}
