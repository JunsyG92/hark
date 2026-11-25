import { contextBridge, ipcRenderer } from 'electron'

export interface HarkBridge {
  api: (req: { method: string; path: string; body?: unknown }) => Promise<{ status: number; body: unknown }>
  getSettings: () => Promise<{ shortcut: string; launchAtLogin: boolean }>
  setSettings: (patch: { shortcut?: string; launchAtLogin?: boolean }) => Promise<{ shortcut: string; launchAtLogin: boolean }>
  hide: () => void
  onShown: (cb: () => void) => () => void
  onTasksChanged: (cb: () => void) => () => void
  platform: string
}

const bridge: HarkBridge = {
  api: (req) => ipcRenderer.invoke('hark:api', req),
  getSettings: () => ipcRenderer.invoke('hark:settings:get'),
  setSettings: (patch) => ipcRenderer.invoke('hark:settings:set', patch),
  hide: () => ipcRenderer.send('hark:hide'),
  onShown: (cb) => {
    const listener = (): void => cb()
    ipcRenderer.on('hark:shown', listener)
    return () => ipcRenderer.removeListener('hark:shown', listener)
  },
  onTasksChanged: (cb) => {
    const listener = (): void => cb()
    ipcRenderer.on('hark:tasks-changed', listener)
    return () => ipcRenderer.removeListener('hark:tasks-changed', listener)
  },
  platform: process.platform,
}

contextBridge.exposeInMainWorld('hark', bridge)
