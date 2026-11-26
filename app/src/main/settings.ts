import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

export interface AppSettings {
  /** Electron accelerator, e.g. "Control+Alt+K". */
  shortcut: string
  launchAtLogin: boolean
  /** Hide the panel when clicking outside it (off = pinned). */
  hideOnBlur: boolean
}

export const DEFAULT_SETTINGS: AppSettings = {
  shortcut: 'Control+Alt+K',
  launchAtLogin: false,
  hideOnBlur: true,
}

const MODIFIERS = new Set([
  'Command', 'Cmd', 'Control', 'Ctrl', 'CommandOrControl', 'CmdOrCtrl',
  'Alt', 'Option', 'AltGr', 'Shift', 'Super', 'Meta',
])
const KEY_RE = /^([A-Z0-9]|F([1-9]|1[0-9]|2[0-4])|Space|Tab|Backspace|Delete|Insert|Return|Enter|Up|Down|Left|Right|Home|End|PageUp|PageDown|Escape|Esc|Plus|[`\-=[\];',./\\])$/

/** Accept only accelerators with ≥1 modifier and exactly one key. */
export function isValidAccelerator(value: string): boolean {
  const parts = value.split('+').map((p) => p.trim())
  if (parts.length < 2 || parts.some((p) => p === '')) return false
  const key = parts[parts.length - 1]!
  const mods = parts.slice(0, -1)
  return mods.every((m) => MODIFIERS.has(m)) && new Set(mods).size === mods.length && KEY_RE.test(key.length === 1 ? key.toUpperCase() : key)
}

export function sanitizeSettings(raw: unknown): AppSettings {
  const out: AppSettings = { ...DEFAULT_SETTINGS }
  if (raw && typeof raw === 'object') {
    const r = raw as Record<string, unknown>
    if (typeof r.shortcut === 'string' && isValidAccelerator(r.shortcut)) out.shortcut = r.shortcut
    if (typeof r.launchAtLogin === 'boolean') out.launchAtLogin = r.launchAtLogin
    if (typeof r.hideOnBlur === 'boolean') out.hideOnBlur = r.hideOnBlur
  }
  return out
}

export class SettingsStore {
  private current: AppSettings

  constructor(private readonly file: string) {
    this.current = this.load()
  }

  get(): AppSettings {
    return { ...this.current }
  }

  update(patch: Partial<AppSettings>): AppSettings {
    this.current = sanitizeSettings({ ...this.current, ...patch })
    mkdirSync(dirname(this.file), { recursive: true })
    writeFileSync(this.file, JSON.stringify(this.current, null, 2))
    return this.get()
  }

  private load(): AppSettings {
    if (!existsSync(this.file)) return { ...DEFAULT_SETTINGS }
    try {
      return sanitizeSettings(JSON.parse(readFileSync(this.file, 'utf8')))
    } catch {
      return { ...DEFAULT_SETTINGS }
    }
  }
}
