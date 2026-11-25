import { BrowserWindow, screen } from 'electron'
import { join } from 'node:path'
import type { RecordingInfo } from './detection'

const WIDTH = 320
const HEIGHT = 84
const MARGIN = 16

/**
 * Always-visible recording indicator (consent requirement): red dot, elapsed time, Stop button
 * and an optional title field. Shown without stealing focus, draggable.
 */
export class OverlayWindow {
  private win: BrowserWindow | null = null
  private ready = false
  private info: RecordingInfo | null = null

  create(): void {
    const win = new BrowserWindow({
      width: WIDTH,
      height: HEIGHT,
      show: false,
      frame: false,
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      focusable: true,
      title: 'Hark — enregistrement',
      backgroundColor: '#20242d',
      webPreferences: {
        preload: join(__dirname, '../preload/overlay.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        spellcheck: false,
        backgroundThrottling: false,
      },
    })
    win.setAlwaysOnTop(true, 'screen-saver')
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
    win.on('close', (e) => {
      if (this.info) e.preventDefault() // cannot be closed while recording: use Stop
    })
    win.webContents.on('will-navigate', (e) => e.preventDefault())
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    win.webContents.once('did-finish-load', () => {
      this.ready = true
    })
    if (process.env.ELECTRON_RENDERER_URL) {
      void win.loadURL(`${process.env.ELECTRON_RENDERER_URL}/overlay.html`)
    } else {
      void win.loadFile(join(__dirname, '../renderer/overlay.html'))
    }
    this.win = win
  }

  get webContents(): Electron.WebContents | undefined {
    return this.win?.webContents
  }

  /** The recording the overlay currently represents (the renderer never supplies the id). */
  get recording(): RecordingInfo | null {
    return this.info
  }

  show(info: RecordingInfo): void {
    const win = this.win
    if (!win) return
    this.info = info
    const send = (): void => {
      const area = screen.getPrimaryDisplay().workArea
      win.setPosition(area.x + area.width - WIDTH - MARGIN, area.y + MARGIN)
      win.webContents.send('hark:overlay:state', info)
      win.showInactive()
    }
    if (this.ready) send()
    else win.webContents.once('did-finish-load', send)
  }

  hide(): void {
    this.info = null
    this.win?.hide()
  }

  destroy(): void {
    this.info = null
    this.win?.destroy()
    this.win = null
  }
}
