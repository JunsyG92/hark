import { contextBridge, ipcRenderer } from 'electron'

export interface OverlayState {
  meetingId: string
  startedAtMs: number
  title: string
}

export interface HarkOverlayBridge {
  onState: (cb: (s: OverlayState) => void) => void
  stop: () => void
  setTitle: (title: string) => void
}

contextBridge.exposeInMainWorld('harkOverlay', {
  onState: (cb) => {
    ipcRenderer.on('hark:overlay:state', (_e, s: OverlayState) => cb(s))
  },
  stop: () => ipcRenderer.send('hark:overlay:stop'),
  setTitle: (title) => ipcRenderer.send('hark:overlay:title', title),
} satisfies HarkOverlayBridge)
