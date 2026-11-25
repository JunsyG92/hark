import './toast.css'

interface Prompt {
  promptId: string
  app: string
  promptSeconds: number
  reminder: string
}

declare global {
  interface Window {
    harkToast: {
      onPrompt: (cb: (p: Prompt) => void) => void
      respond: (promptId: string, action: 'record' | 'decline' | 'ignore') => void
    }
  }
}

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T
let current: string | null = null
let timer: number | undefined

function answer(action: 'record' | 'decline' | 'ignore'): void {
  if (!current) return
  const id = current
  current = null
  window.clearTimeout(timer)
  window.harkToast.respond(id, action)
}

window.harkToast.onPrompt((p) => {
  window.clearTimeout(timer)
  current = p.promptId
  $('t-app').textContent = p.app && p.app !== 'test' ? `(${p.app})` : p.app === 'test' ? '(test)' : ''
  $('t-reminder').textContent = p.reminder
  const bar = $('t-bar')
  bar.style.animation = 'none'
  void bar.offsetWidth // restart the animation
  bar.style.animation = `drain ${p.promptSeconds}s linear forwards`
  timer = window.setTimeout(() => answer('ignore'), p.promptSeconds * 1000)
  $('b-record').focus({ preventScroll: true })
})

$('b-record').addEventListener('click', () => answer('record'))
$('b-decline').addEventListener('click', () => answer('decline'))
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') answer('ignore')
})
