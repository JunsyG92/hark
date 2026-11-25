import type { DetectionPhase } from './detection-types'

export const PHASE_LABEL: Record<DetectionPhase, string> = {
  disabled: 'Détection désactivée',
  idle: 'En écoute (rien n’est enregistré)',
  prompted: 'Notification affichée',
  cooldown: 'En pause après ton choix',
  recording: 'Enregistrement en cours',
}

export function blockerText(code: string, cooldownSeconds: number): string {
  switch (code) {
    case 'disabled': return 'La détection est désactivée.'
    case 'prompt_showing': return 'Une notification est affichée : réponds-y.'
    case 'recording': return 'Un enregistrement est en cours.'
    case 'cooldown': return `En pause après ta réponse précédente (encore ${Math.max(1, Math.ceil(cooldownSeconds / 60))} min).`
    case 'no_audio': return 'Aucun son mesuré : l’écoute de la sortie audio est indisponible.'
    case 'below_threshold': return 'Le son est sous le seuil : baisse le seuil ou monte le volume.'
    case 'waiting_duration': return 'Son au-dessus du seuil, mais la durée minimale n’est pas encore atteinte.'
    case 'mic_not_in_use': return 'Aucune application n’utilise le micro (une vidéo seule ne déclenche rien). Décoche « Exiger… » pour tester.'
    default: return code
  }
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
