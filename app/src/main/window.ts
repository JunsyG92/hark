import { BrowserWindow, screen, shell } from 'electron'
import { shouldHideOnBlur } from './blur'
import { panelBounds } from './panelGeometry'
import { join } from 'node:path'

/**
 * The kanban is a side panel docked on the right of the screen (frameless, transparent around a
 * rounded surface, like aska). It is created once at startup and kept hidden, so the global shortcut
 * only has to show() it: that is what keeps the open time < 300 ms.
 */
export class KanbanWindow {
  private win: BrowserWindow | null = null
  private quitting = false
  private shownAt = 0
  private dialogDepth = 0

  constructor(
    private readonly log: (msg: string) => void,
    private readonly hideOnBlur: () => boolean = () => true,
  ) {}

  create(): BrowserWindow {
    const area = screen.getPrimaryDisplay().workArea
    const win = new BrowserWindow({
      ...panelBounds(area),
      show: false,
      frame: false,
      transparent: true,
      backgroundColor: '#00000000',
      hasShadow: false, // the shadow is drawn by the page, inside the transparent margin
      resizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      title: 'Hark',
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

    // Click outside: the panel hides (unless pinned, or focus went to something of its own).
    win.on('blur', () => {
      const hide = shouldHideOnBlur({
        enabled: this.hideOnBlur(),
        visible: win.isVisible(),
        dialogOpen: this.dialogDepth > 0,
        devToolsOpen: win.webContents.isDevToolsOpened(),
        msSinceShow: Date.now() - this.shownAt,
        cursor: screen.getCursorScreenPoint(),
        bounds: win.getBounds(),
      })
      if (hide) win.hide()
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
    // follow the user: dock on the screen where the cursor is
    win.setBounds(panelBounds(screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea))
    this.shownAt = Date.now()
    win.show()
    win.focus()
    win.webContents.send('hark:shown')
    this.log(`kanban shown in ${(performance.now() - t0).toFixed(1)} ms`)
  }

  hide(): void {
    this.win?.hide()
  }

  /** Run a native dialog without the panel hiding behind it (the dialog takes the focus). */
  async withDialog<T>(run: (win: BrowserWindow | null) => Promise<T>): Promise<T> {
    this.dialogDepth += 1
    try {
      return await run(this.win)
    } finally {
      this.dialogDepth -= 1
      this.win?.focus()
    }
  }

  get window(): BrowserWindow | null {
    return this.win
  }

  get webContents(): Electron.WebContents | undefined {
    return this.win?.webContents
  }

  setQuitting(): void {
    this.quitting = true
  }
}
