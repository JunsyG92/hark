import './overlay.css'

export interface OverlayState {
  meetingId: string
  startedAtMs: number
  title: string
}

export interface OverlayBridge {
  onState: (cb: (s: OverlayState) => void) => void
  stop: () => void
  setTitle: (title: string) => void
}

declare global {
  interface Window {
    harkOverlay: OverlayBridge
  }
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function initOverlay(doc: Document, bridge: OverlayBridge, now: () => number = Date.now): void {
  const time = doc.getElementById('o-time') as HTMLElement
  const title = doc.getElementById('o-title') as HTMLInputElement
  let started = now()
  let sent = ''
  window.setInterval(() => {
    time.textContent = formatElapsed(now() - started)
  }, 1000)

  bridge.onState((s) => {
    started = s.startedAtMs
    title.value = s.title
    sent = s.title
    time.textContent = formatElapsed(now() - started)
  })

  const commit = (): void => {
    const value = title.value.trim()
    if (value !== sent) {
      sent = value
      bridge.setTitle(value)
    }
  }
  title.addEventListener('blur', commit)
  title.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      commit()
      title.blur()
    }
  })
  ;(doc.getElementById('o-stop') as HTMLElement).addEventListener('click', () => {
    commit()
    bridge.stop()
  })
}

if (typeof window !== 'undefined' && window.harkOverlay) initOverlay(document, window.harkOverlay)
