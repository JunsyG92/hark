import { useEffect, useMemo, useState } from 'react'
import { createApi, type RecordingSettings, type RecordingStatus } from '../lib/api'
import { levelLabel } from '../lib/recording'

export function RecordingSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [settings, setSettings] = useState<RecordingSettings | null>(null)
  const [status, setStatus] = useState<RecordingStatus | null>(null)

  useEffect(() => {
    let alive = true
    void api.recordingSettings().then((s) => alive && setSettings(s)).catch(() => undefined)
    const tick = () => void api.recordingStatus().then((s) => alive && setStatus(s)).catch(() => undefined)
    tick()
    const id = window.setInterval(tick, 1000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [api])

  async function patch(p: Partial<RecordingSettings>) {
    try {
      setSettings(await api.patchRecordingSettings(p))
    } catch {
      /* out-of-range values are rejected by the engine; keep the previous value */
    }
  }

  if (!settings) return null
  return (
    <fieldset className="detect">
      <legend>Enregistrement</legend>
      <p className="modal__source">
        Deux pistes (sortie système = les autres, micro = moi) enregistrées en local (WAV 16 kHz). Jamais
        d’enregistrement sans ton clic.
      </p>
      <label>
        « Réunion terminée ? » après un silence de (minutes)
        <input type="number" min={1} max={30} value={settings.silence_minutes} onChange={(e) => e.target.value && void patch({ silence_minutes: Number(e.target.value) })} />
      </label>
      <label>
        Niveau considéré comme du silence : {Math.round(settings.silence_threshold_db)} dB
        <input type="range" min={-80} max={-10} value={settings.silence_threshold_db} onChange={(e) => void patch({ silence_threshold_db: Number(e.target.value) })} />
      </label>
      <p className="modal__source">
        {status?.recording
          ? `En cours · système ${levelLabel(status.system_level_db)} · micro ${levelLabel(status.mic_level_db)} · silence depuis ${Math.round(status.silent_seconds)} s`
          : 'Aucun enregistrement en cours.'}
      </p>
      {status?.warnings.map((w) => (
        <p key={w} className="modal__error">{w}</p>
      ))}
    </fieldset>
  )
}
