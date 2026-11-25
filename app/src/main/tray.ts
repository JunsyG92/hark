import { Menu, Tray, nativeImage } from 'electron'
import { join } from 'node:path'

export interface TrayActions {
  openKanban: () => void
  toggleLaunchAtLogin: (enabled: boolean) => void
  quit: () => void
}

export type TrayState = 'idle' | 'recording'

export class AppTray {
  private tray: Tray | null = null
  private state: TrayState = 'idle'

  constructor(
    private readonly actions: TrayActions,
    private readonly getInfo: () => { shortcut: string; launchAtLogin: boolean },
  ) {}

  private icon(state: TrayState): Electron.NativeImage {
    const file = state === 'recording' ? 'tray-rec.png' : 'tray-idle.png'
    return nativeImage.createFromPath(join(__dirname, '../../assets', file))
  }

  create(): void {
    this.tray = new Tray(this.icon('idle'))
    this.tray.setToolTip('Hark')
    this.tray.on('click', () => this.actions.openKanban())
    this.refreshMenu()
  }

  setState(state: TrayState): void {
    this.state = state
    this.tray?.setImage(this.icon(state))
    this.tray?.setToolTip(state === 'recording' ? 'Hark — enregistrement en cours' : 'Hark')
    this.refreshMenu()
  }

  refreshMenu(): void {
    const { shortcut, launchAtLogin } = this.getInfo()
    this.tray?.setContextMenu(
      Menu.buildFromTemplate([
        { label: 'Ouvrir le kanban', accelerator: shortcut, click: () => this.actions.openKanban() },
        { type: 'separator' },
        {
          label: 'Lancer au démarrage',
          type: 'checkbox',
          checked: launchAtLogin,
          click: (item) => this.actions.toggleLaunchAtLogin(item.checked),
        },
        { type: 'separator' },
        { label: this.state === 'recording' ? '● Enregistrement…' : 'Aucun enregistrement', enabled: false },
        { label: 'Quitter Hark', click: () => this.actions.quit() },
      ]),
    )
  }
}
