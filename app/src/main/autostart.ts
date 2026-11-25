import { app } from 'electron'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

/** Linux has no login-item API in Electron: use an XDG autostart entry. */
function linuxDesktopFile(): string {
  const base = process.env.XDG_CONFIG_HOME || join(homedir(), '.config')
  return join(base, 'autostart', 'hark.desktop')
}

export function desktopEntry(execPath: string): string {
  return [
    '[Desktop Entry]',
    'Type=Application',
    'Name=Hark',
    'Comment=Local meeting assistant',
    `Exec="${execPath}" --hidden`,
    'X-GNOME-Autostart-enabled=true',
    'NoDisplay=false',
    '',
  ].join('\n')
}

export function setLaunchAtLogin(enabled: boolean): void {
  if (process.platform === 'linux') {
    const file = linuxDesktopFile()
    if (enabled) {
      mkdirSync(join(file, '..'), { recursive: true })
      writeFileSync(file, desktopEntry(process.env.APPIMAGE || process.execPath))
    } else if (existsSync(file)) {
      rmSync(file)
    }
    return
  }
  app.setLoginItemSettings({ openAtLogin: enabled, args: ['--hidden'] })
}
