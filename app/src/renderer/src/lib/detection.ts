import type { DetectionPhase } from './detection-types'

export const PHASE_LABEL: Record<DetectionPhase, string> = {
  disabled: 'Détection désactivée',
  idle: 'En écoute (rien n’est enregistré)',
  prompted: 'Notification affichée',
  cooldown: 'En pause après ton choix',
  recording: 'Enregistrement en cours',
}

/** Map dBFS (-80..0) to a 0..100 % bar width. */
export function dbToPercent(db: number | null): number {
  if (db === null) return 0
  return Math.max(0, Math.min(100, ((db + 80) / 80) * 100))
}

export function micLabel(inUse: boolean | null, apps: string[]): string {
  if (inUse === null) return 'inconnu (non pris en charge sur ce système)'
  if (!inUse) return 'non'
  return apps.length ? `oui (${apps.join(', ')})` : 'oui'
}
