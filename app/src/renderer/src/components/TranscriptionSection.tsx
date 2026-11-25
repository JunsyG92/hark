import { useCallback, useEffect, useMemo, useState } from 'react'
import { createApi, type ModelProfile, type TranscriptionSettings } from '../lib/api'
import type { TranscriptionStatusInfo } from '../lib/api'

const RETENTION = [
  { value: 0, label: 'Supprimer l’audio dès que la transcription est réussie (recommandé)' },
  { value: 7, label: 'Garder l’audio 7 jours' },
  { value: 30, label: 'Garder l’audio 30 jours' },
] as const

export function TranscriptionSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [settings, setSettings] = useState<TranscriptionSettings | null>(null)
  const [models, setModels] = useState<ModelProfile[]>([])
  const [status, setStatus] = useState<TranscriptionStatusInfo | null>(null)

  const refreshModels = useCallback(async () => {
    try {
      setModels(await api.models())
    } catch {
      /* engine unreachable */
    }
  }, [api])

  useEffect(() => {
    let alive = true
    void api.transcriptionSettings().then((s) => alive && setSettings(s)).catch(() => undefined)
    void refreshModels()
    const tick = () =>
      void api.transcriptionStatus().then((s) => {
        if (!alive) return
        setStatus((prev) => {
          if (prev?.download.state === 'downloading' && s.download.state !== 'downloading') void refreshModels()
          return s
        })
      }).catch(() => undefined)
    tick()
    const id = window.setInterval(tick, 1500)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [api, refreshModels])

  async function patch(p: Partial<TranscriptionSettings>) {
    try {
      setSettings(await api.patchTranscriptionSettings(p))
    } catch {
      /* rejected by the engine: keep the previous value */
    }
  }

  if (!settings) return null
  const downloading = status?.download.state === 'downloading'
  return (
    <fieldset className="detect">
      <legend>Transcription (100 % locale)</legend>
      <p className="modal__source">
        Choisis le modèle selon ta machine. Un modèle plus gros est plus précis mais plus lent. Le téléchargement est la
        seule connexion réseau de Hark (depuis Hugging Face, aucune donnée envoyée) ; il ne se fait que si tu cliques.
      </p>
      <div role="radiogroup" aria-label="Modèle de transcription" className="models">
        {models.map((m) => (
          <label key={m.id} className={`model${settings.profile === m.id ? ' model--on' : ''}`}>
            <input type="radio" name="profile" checked={settings.profile === m.id} onChange={() => void patch({ profile: m.id })} />
            <span className="model__body">
              <strong>{m.label}</strong>
              {m.recommended && <span className="pill pill--mine">recommandé pour cette machine</span>}
              <span className="model__desc">{m.description}</span>
              <span className="model__desc">≈ {m.download_mb} Mo · {m.min_ram_gb} Go de RAM conseillés{m.gpu_recommended ? ' · carte graphique conseillée' : ''}</span>
            </span>
            {m.installed ? (
              <span className="pill">installé ✓</span>
            ) : (
              <button type="button" className="btn" disabled={downloading} onClick={() => void api.downloadModel(m.id).then(() => api.transcriptionStatus().then(setStatus))}>
                {downloading && status?.download.profile === m.id ? 'Téléchargement…' : 'Télécharger'}
              </button>
            )}
          </label>
        ))}
      </div>
      {status?.download.state === 'error' && <p className="modal__error">Téléchargement impossible : {status.download.error}</p>}
      <label>
        Langue
        <select value={settings.language} onChange={(e) => void patch({ language: e.target.value as TranscriptionSettings['language'] })}>
          <option value="auto">Détection automatique (français / anglais)</option>
          <option value="fr">Français</option>
          <option value="en">Anglais</option>
        </select>
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={settings.auto_transcribe} onChange={(e) => void patch({ auto_transcribe: e.target.checked })} />
        Transcrire automatiquement à la fin de chaque enregistrement
      </label>
      <label>
        Audio après transcription
        <select value={settings.retention_days} onChange={(e) => void patch({ retention_days: Number(e.target.value) as TranscriptionSettings['retention_days'] })}>
          {RETENTION.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </label>
      {status?.current_meeting_id && <p className="modal__source">Transcription en cours : {Math.round(status.progress * 100)} %</p>}
    </fieldset>
  )
}
