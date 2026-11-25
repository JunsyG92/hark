import { contextBridge, ipcRenderer } from 'electron'

export interface ToastPrompt {
  promptId: string
  app: string
  promptSeconds: number
  reminder: string
}

export interface HarkToastBridge {
  onPrompt: (cb: (p: ToastPrompt) => void) => void
  respond: (promptId: string, action: 'record' | 'decline' | 'ignore') => void
}

// The toast gets the smallest possible surface: receive a prompt, send one answer.
const bridge: HarkToastBridge = {
  onPrompt: (cb) => {
    ipcRenderer.on('hark:toast:prompt', (_e, p: ToastPrompt) => cb(p))
  },
  respond: (promptId, action) => ipcRenderer.send('hark:toast:respond', { promptId, action }),
}

contextBridge.exposeInMainWorld('harkToast', bridge)
