import { contextBridge, ipcRenderer } from 'electron'

export interface HarkBridge {
  api: (req: { method: string; path: string; body?: unknown }) => Promise<{ status: number; body: unknown }>
  getSettings: () => Promise<{ shortcut: string; launchAtLogin: boolean; hideOnBlur: boolean }>
  setSettings: (patch: { shortcut?: string; launchAtLogin?: boolean; hideOnBlur?: boolean }) => Promise<{ shortcut: string; launchAtLogin: boolean; hideOnBlur: boolean }>
  confirm: (req: { message: string; detail?: string; confirmLabel?: string }) => Promise<boolean>
  hide: () => void
  onShown: (cb: () => void) => () => void
  onTasksChanged: (cb: () => void) => () => void
  onRecordingChanged: (cb: () => void) => () => void
  onMeetingsChanged: (cb: () => void) => () => void
  saveFile: (suggestedName: string, content: string) => Promise<{ saved: boolean }>
  platform: string
}

const bridge: HarkBridge = {
  api: (req) => ipcRenderer.invoke('hark:api', req),
  getSettings: () => ipcRenderer.invoke('hark:settings:get'),
  setSettings: (patch) => ipcRenderer.invoke('hark:settings:set', patch),
  hide: () => ipcRenderer.send('hark:hide'),
  confirm: (req) => ipcRenderer.invoke('hark:confirm', req),
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
  onRecordingChanged: (cb) => {
    const listener = (): void => cb()
    ipcRenderer.on('hark:recording-changed', listener)
    return () => ipcRenderer.removeListener('hark:recording-changed', listener)
  },
  onMeetingsChanged: (cb) => {
    const listener = (): void => cb()
    ipcRenderer.on('hark:meetings-changed', listener)
    return () => ipcRenderer.removeListener('hark:meetings-changed', listener)
  },
  saveFile: (suggestedName, content) => ipcRenderer.invoke('hark:save-file', { suggestedName, content }),
  platform: process.platform,
}

contextBridge.exposeInMainWorld('hark', bridge)
