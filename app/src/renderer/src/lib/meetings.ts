import type { Meeting } from './contracts.gen'

const pad = (n: number): string => String(n).padStart(2, '0')

export function displayTitle(m: Pick<Meeting, 'title' | 'started_at'>): string {
  if (m.title.trim()) return m.title.trim()
  const d = new Date(m.started_at)
  return `Réunion du ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function durationLabel(ms: number | null): string {
  if (!ms) return '—'
  const min = Math.max(1, Math.round(ms / 60000))
  return min >= 60 ? `${Math.floor(min / 60)} h ${pad(min % 60)}` : `${min} min`
}

export function timestamp(ms: number): string {
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  return `${h ? `${h}:` : ''}${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`
}

export function transcriptionLabel(m: Pick<Meeting, 'status' | 'transcription' | 'transcription_error'>): string {
  if (m.status === 'recording') return 'enregistrement en cours'
  if (m.status === 'failed') return 'enregistrement vide'
  switch (m.transcription) {
    case 'done': return 'transcription prête'
    case 'running': return 'transcription en cours…'
    case 'pending': return m.transcription_error === 'model_not_installed' ? 'en attente d’un modèle' : 'en file d’attente'
    case 'failed': return 'transcription en échec'
    default: return 'non transcrite'
  }
}

export interface SnippetPart { text: string; match: boolean }

/** Split an FTS snippet into plain/match parts. Only <mark> is interpreted; everything else is text. */
export function parseSnippet(snippet: string): SnippetPart[] {
  const parts: SnippetPart[] = []
  for (const piece of snippet.split(/(<mark>.*?<\/mark>)/s)) {
    if (!piece) continue
    const m = /^<mark>(.*)<\/mark>$/s.exec(piece)
    parts.push(m ? { text: m[1]!, match: true } : { text: piece, match: false })
  }
  return parts
}

/** encodeURIComponent plus the few characters our API path whitelist does not allow. */
export function enc(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*~]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`)
}
