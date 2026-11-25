import './toast.css'

export interface Prompt {
  kind: 'consent' | 'ended'
  promptId: string
  app: string
  promptSeconds: number
  silenceMinutes: number
  reminder: string
}

export type Answer = 'record' | 'decline' | 'ignore' | 'stop' | 'continue'

export interface Bridge {
  onPrompt: (cb: (p: Prompt) => void) => void
  respond: (promptId: string, action: Answer) => void
}

declare global {
  interface Window {
    harkToast: Bridge
  }
}

/** Wire the toast DOM to its bridge. Exported for tests. */
export function initToast(doc: Document, bridge: Bridge): void {
  const $ = <T extends HTMLElement>(id: string): T => doc.getElementById(id) as T
  let current: Prompt | null = null
  let timer: number | undefined
  const [primary, secondary] = [$('b-primary'), $('b-secondary')]

  function answer(action: Answer): void {
    if (!current) return
    const id = current.promptId
    current = null
    window.clearTimeout(timer)
    bridge.respond(id, action)
  }

  bridge.onPrompt((p) => {
    window.clearTimeout(timer)
    current = p
    const bar = $('t-bar')
    if (p.kind === 'consent') {
      $('t-title').textContent = 'Réunion détectée'
      $('t-text').textContent = 'Enregistrer cette réunion ? '
      const app = doc.createElement('span')
      app.id = 't-app'
      app.textContent = p.app === 'test' ? '(test)' : p.app ? `(${p.app})` : ''
      $('t-text').appendChild(app)
      $('t-reminder').textContent = p.reminder
      primary.textContent = 'Enregistrer'
      secondary.textContent = 'Non'
      bar.style.display = ''
      bar.style.animation = 'none'
      void bar.offsetWidth // restart the animation
      bar.style.animation = `drain ${p.promptSeconds}s linear forwards`
      timer = window.setTimeout(() => answer('ignore'), p.promptSeconds * 1000)
    } else {
      // "Réunion terminée ?": stays on screen until a voice returns (main hides it) or the user answers.
      $('t-title').textContent = 'Réunion terminée ?'
      $('t-text').textContent = `Silence depuis ${p.silenceMinutes} min. L’enregistrement continue.`
      $('t-reminder').textContent = 'Cette fenêtre se ferme si quelqu’un reparle.'
      primary.textContent = 'Arrêter'
      secondary.textContent = 'Continuer'
      bar.style.display = 'none'
    }
    primary.focus({ preventScroll: true })
  })

  primary.addEventListener('click', () => answer(current?.kind === 'ended' ? 'stop' : 'record'))
  secondary.addEventListener('click', () => answer(current?.kind === 'ended' ? 'continue' : 'decline'))
  doc.defaultView?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') answer(current?.kind === 'ended' ? 'continue' : 'ignore')
  })
}

if (typeof window !== 'undefined' && window.harkToast) initToast(document, window.harkToast)
