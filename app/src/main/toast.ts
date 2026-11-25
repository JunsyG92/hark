import { BrowserWindow, screen } from 'electron'
import { join } from 'node:path'
import type { DetectedPrompt } from './detection'

const WIDTH = 380
const HEIGHT = 178
const MARGIN = 16

/**
 * Consent toast. Always on top, shown WITHOUT taking focus (so typing in the meeting window is
 * never hijacked), identical on every OS (native notification actions are unreliable on Linux).
 */
export class ToastWindow {
  private win: BrowserWindow | null = null
  private ready = false

  create(): void {
    const win = new BrowserWindow({
      width: WIDTH,
      height: HEIGHT,
      show: false,
      frame: false,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      focusable: true,
      title: 'Hark — réunion détectée',
      backgroundColor: '#20242d',
      webPreferences: {
        preload: join(__dirname, '../preload/toast.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        spellcheck: false,
      },
    })
    win.setAlwaysOnTop(true, 'screen-saver')
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    win.webContents.on('will-navigate', (e) => e.preventDefault())
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    win.webContents.once('did-finish-load', () => {
      this.ready = true
    })
    if (process.env.ELECTRON_RENDERER_URL) {
      void win.loadURL(`${process.env.ELECTRON_RENDERER_URL}/toast.html`)
    } else {
      void win.loadFile(join(__dirname, '../renderer/toast.html'))
    }
    this.win = win
  }

  get webContents(): Electron.WebContents | undefined {
    return this.win?.webContents
  }

  show(prompt: DetectedPrompt): void {
    const win = this.win
    if (!win) return
    const send = (): void => {
      const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
      win.setPosition(area.x + area.width - WIDTH - MARGIN, area.y + area.height - HEIGHT - MARGIN)
      win.webContents.send('hark:toast:prompt', prompt)
      win.showInactive()
    }
    if (this.ready) send()
    else win.webContents.once('did-finish-load', send)
  }

  hide(): void {
    this.win?.hide()
  }

  destroy(): void {
    this.win?.destroy()
    this.win = null
  }
}
