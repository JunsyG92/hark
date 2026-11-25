import { contextBridge, ipcRenderer } from 'electron'

export interface ToastPrompt {
  kind: 'consent' | 'ended'
  promptId: string
  app: string
  promptSeconds: number
  silenceMinutes: number
  reminder: string
}

export type ToastAnswer = 'record' | 'decline' | 'ignore' | 'stop' | 'continue'

export interface HarkToastBridge {
  onPrompt: (cb: (p: ToastPrompt) => void) => void
  respond: (promptId: string, action: ToastAnswer) => void
}

// The toast gets the smallest possible surface: receive a prompt, send one answer.
const bridge: HarkToastBridge = {
  onPrompt: (cb) => {
    ipcRenderer.on('hark:toast:prompt', (_e, p: ToastPrompt) => cb(p))
  },
  respond: (promptId, action) => ipcRenderer.send('hark:toast:respond', { promptId, action }),
}

contextBridge.exposeInMainWorld('harkToast', bridge)
