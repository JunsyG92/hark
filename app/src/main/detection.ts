/** Validation of data crossing the engine → toast and toast → main boundaries. */

export const CONSENT_ACTIONS = ['record', 'decline', 'ignore'] as const
export const ENDED_ACTIONS = ['stop', 'continue'] as const
export type ToastAction = (typeof CONSENT_ACTIONS)[number] | (typeof ENDED_ACTIONS)[number]
export type ToastKind = 'consent' | 'ended'

/** What the toast window displays. `promptId` is the detection prompt or the meeting id. */
export interface ToastPayload {
  kind: ToastKind
  promptId: string
  app: string
  /** Consent: seconds before it counts as "ignore". Ended: 0 (stays until answered / voice back). */
  promptSeconds: number
  /** Ended: whole minutes of silence so far. */
  silenceMinutes: number
  reminder: string
}

const ID_OK = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 64

export function parseDetected(data: Record<string, unknown>): ToastPayload | null {
  const { prompt_id: id, app, prompt_seconds: secs, reminder } = data
  if (!ID_OK(id)) return null
  if (typeof secs !== 'number' || !Number.isFinite(secs) || secs < 1 || secs > 300) return null
  return {
    kind: 'consent',
    promptId: id,
    app: typeof app === 'string' ? app.slice(0, 80) : '',
    promptSeconds: secs,
    silenceMinutes: 0,
    reminder: typeof reminder === 'string' ? reminder.slice(0, 200) : 'Pense à informer les participants.',
  }
}

export interface SilenceEvent {
  meetingId: string
  silent: boolean
  silenceSeconds: number
}

export function parseSilence(data: Record<string, unknown>): SilenceEvent | null {
  const { meeting_id: id, silent, silence_seconds: secs } = data
  if (!ID_OK(id) || typeof silent !== 'boolean') return null
  return { meetingId: id, silent, silenceSeconds: typeof secs === 'number' && Number.isFinite(secs) ? secs : 0 }
}

export function endedPayload(e: SilenceEvent): ToastPayload {
  return {
    kind: 'ended',
    promptId: e.meetingId,
    app: '',
    promptSeconds: 0,
    silenceMinutes: Math.max(1, Math.round(e.silenceSeconds / 60)),
    reminder: '',
  }
}

export interface RecordingInfo {
  meetingId: string
  startedAtMs: number
  title: string
}

export function parseRecordingStarted(data: Record<string, unknown>): RecordingInfo | null {
  const m = data.meeting as Record<string, unknown> | undefined
  if (!m || !ID_OK(m.id) || typeof m.started_at !== 'string') return null
  const startedAtMs = Date.parse(m.started_at)
  if (!Number.isFinite(startedAtMs)) return null
  return { meetingId: m.id, startedAtMs, title: typeof m.title === 'string' ? m.title.slice(0, 200) : '' }
}

export function allowedActions(kind: ToastKind): readonly ToastAction[] {
  return kind === 'consent' ? CONSENT_ACTIONS : ENDED_ACTIONS
}

export function parseToastResponse(raw: unknown): { promptId: string; action: ToastAction } | null {
  if (!raw || typeof raw !== 'object') return null
  const { promptId, action } = raw as Record<string, unknown>
  if (!ID_OK(promptId)) return null
  const all: readonly string[] = [...CONSENT_ACTIONS, ...ENDED_ACTIONS]
  if (typeof action !== 'string' || !all.includes(action)) return null
  return { promptId, action: action as ToastAction }
}

export function parseTitle(raw: unknown): string | null {
  return typeof raw === 'string' && raw.length <= 200 ? raw.trim() : null
}
