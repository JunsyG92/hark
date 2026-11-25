import { BrowserWindow, shell } from 'electron'
import { join } from 'node:path'

/**
 * The kanban window is created once at startup and kept hidden, so the global
 * shortcut only has to show() it: that is what keeps the open time < 300 ms.
 */
export class KanbanWindow {
  private win: BrowserWindow | null = null
  private quitting = false

  constructor(private readonly log: (msg: string) => void) {}

  create(): BrowserWindow {
    const win = new BrowserWindow({
      width: 1180,
      height: 760,
      minWidth: 720,
      minHeight: 480,
      show: false,
      title: 'Hark',
      backgroundColor: '#111318',
      autoHideMenuBar: true,
      icon: join(__dirname, '../../assets/icon.png'),
      webPreferences: {
        preload: join(__dirname, '../preload/index.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        spellcheck: false,
        backgroundThrottling: false,
      },
    })

    win.on('close', (e) => {
      if (!this.quitting) {
        e.preventDefault()
        win.hide()
      }
    })
    // No navigation, no popups: external links open in the OS browser.
    win.webContents.on('will-navigate', (e) => e.preventDefault())
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (/^https?:\/\//.test(url)) void shell.openExternal(url)
      return { action: 'deny' }
    })

    if (process.env.ELECTRON_RENDERER_URL) {
      void win.loadURL(process.env.ELECTRON_RENDERER_URL)
    } else {
      void win.loadFile(join(__dirname, '../renderer/index.html'))
    }
    this.win = win
    return win
  }

  toggle(): void {
    const win = this.win
    if (!win) return
    if (win.isVisible() && win.isFocused()) {
      win.hide()
      return
    }
    this.show()
  }

  show(): void {
    const win = this.win
    if (!win) return
    const t0 = performance.now()
    if (win.isMinimized()) win.restore()
    win.show()
    win.focus()
    win.webContents.send('hark:shown')
    this.log(`kanban shown in ${(performance.now() - t0).toFixed(1)} ms`)
  }

  hide(): void {
    this.win?.hide()
  }

  get webContents(): Electron.WebContents | undefined {
    return this.win?.webContents
  }

  setQuitting(): void {
    this.quitting = true
  }
}
