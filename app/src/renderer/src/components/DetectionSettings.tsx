import { useEffect, useMemo, useState } from 'react'
import { createApi, type DetectionSettings, type DetectionStatus } from '../lib/api'
import { PHASE_LABEL, blockerText, dbToPercent, micLabel } from '../lib/detection'

/** Live meter + tuning for meeting detection. Observation only: nothing is recorded here. */
export function DetectionSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [settings, setSettings] = useState<DetectionSettings | null>(null)
  const [status, setStatus] = useState<DetectionStatus | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    void api.detectionSettings().then((s) => alive && setSettings(s)).catch(() => undefined)
    const tick = () => void api.detectionStatus().then((s) => alive && setStatus(s)).catch(() => undefined)
    tick()
    const id = window.setInterval(tick, 1000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [api])

  async function patch(p: Partial<DetectionSettings>) {
    try {
      setSettings(await api.patchDetectionSettings(p))
      setNote(null)
    } catch (err) {
      setNote(String((err as Error).message))
    }
  }

  async function test() {
    const res = await api.testDetectionPrompt()
    setNote(res.prompted ? 'Notification de test envoyée (rien n’est enregistré).' : 'Une notification est déjà en cours ou en pause.')
  }

  if (!settings) return null
  const level = status?.level_db ?? null
  return (
    <fieldset className="detect">
      <legend>Détection des réunions</legend>
      <label className="checkbox">
        <input type="checkbox" checked={settings.enabled} onChange={(e) => void patch({ enabled: e.target.checked })} />
        Me proposer d’enregistrer quand une réunion est probable
      </label>
      {status && (
        <div className="meter" aria-label="Niveau audio de la sortie système">
          <div className="meter__bar">
            <div className="meter__fill" style={{ width: `${dbToPercent(level)}%` }} />
            <div className="meter__threshold" style={{ left: `${dbToPercent(settings.threshold_db)}%` }} />
          </div>
          <p className="modal__source">
            {status.audio_source
              ? `Niveau : ${level === null ? '—' : `${Math.round(level)} dB`} · seuil ${Math.round(settings.threshold_db)} dB · au-dessus depuis ${status.above_threshold_seconds} s`
              : 'Écoute audio désactivée'}
            <br />
            Micro utilisé par une autre application : {micLabel(status.mic_in_use, status.mic_apps)}
            <br />
            État : {PHASE_LABEL[status.phase]}
          </p>
          {status.error && <p className="modal__error">Audio indisponible : {status.error}</p>}
          {status.mic_probe_error && (
            <p className="modal__source">Lecture de l’état du micro impossible ({status.mic_probe_error}) : la notification n’est pas filtrée.</p>
          )}
          {status.blockers.length > 0 && (
            <p className="modal__source" data-testid="blockers">
              Pas de notification pour l’instant :
              {status.blockers.map((b) => (
                <span key={b}><br />• {blockerText(b, status.cooldown_remaining_s)}</span>
              ))}
            </p>
          )}
        </div>
      )}
      <label>
        Seuil sonore : {Math.round(settings.threshold_db)} dB
        <input type="range" min={-80} max={-10} value={settings.threshold_db} onChange={(e) => void patch({ threshold_db: Number(e.target.value) })} />
      </label>
      <label>
        Durée avant de proposer (secondes)
        <input type="number" min={1} max={120} value={settings.min_seconds} onChange={(e) => e.target.value && void patch({ min_seconds: Number(e.target.value) })} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={settings.require_mic_in_use} onChange={(e) => void patch({ require_mic_in_use: e.target.checked })} />
        Exiger qu’une application utilise le micro (évite les vidéos seules)
      </label>
      <div className="modal__actions">
        <button type="button" className="btn" onClick={() => void test()}>
          Tester la notification
        </button>
      </div>
      {note && <p className="modal__source">{note}</p>}
    </fieldset>
  )
}
