/** Validation of data crossing the engine → toast and toast → main boundaries. */

export interface DetectedPrompt {
  promptId: string
  app: string
  promptSeconds: number
  reminder: string
}

export const PROMPT_ACTIONS = ['record', 'decline', 'ignore'] as const
export type PromptAction = (typeof PROMPT_ACTIONS)[number]

export function parseDetected(data: Record<string, unknown>): DetectedPrompt | null {
  const { prompt_id: id, app, prompt_seconds: secs, reminder } = data
  if (typeof id !== 'string' || id.length === 0 || id.length > 64) return null
  if (typeof secs !== 'number' || !Number.isFinite(secs) || secs < 1 || secs > 300) return null
  return {
    promptId: id,
    app: typeof app === 'string' ? app.slice(0, 80) : '',
    promptSeconds: secs,
    reminder: typeof reminder === 'string' ? reminder.slice(0, 200) : 'Pense à informer les participants.',
  }
}

export function parseToastResponse(raw: unknown): { promptId: string; action: PromptAction } | null {
  if (!raw || typeof raw !== 'object') return null
  const { promptId, action } = raw as Record<string, unknown>
  if (typeof promptId !== 'string' || promptId.length === 0 || promptId.length > 64) return null
  if (!PROMPT_ACTIONS.includes(action as PromptAction)) return null
  return { promptId, action: action as PromptAction }
}
