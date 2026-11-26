import { useEffect, useMemo, useState } from 'react'
import { createApi, type ProgressSettings } from '../lib/api'

export function ProgressSection() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [cfg, setCfg] = useState<ProgressSettings | null>(null)

  useEffect(() => {
    void api.progressSettings().then(setCfg).catch(() => undefined)
  }, [api])

  async function patch(p: Partial<ProgressSettings>) {
    try {
      setCfg(await api.patchProgressSettings(p))
    } catch {
      /* out of range: keep the previous value */
    }
  }

  if (!cfg) return null
  return (
    <fieldset className="detect">
      <legend>Progression</legend>
      <p className="modal__source">
        Points, séries, niveaux et badges pour <strong>tes</strong> tâches terminées (les tâches de l’équipe sont comptées à
        part, sans points ni classement). Rien ne récompense l’enregistrement des réunions. Tout reste sur ta machine.
      </p>
      <label className="checkbox">
        <input type="checkbox" checked={cfg.enabled} onChange={(e) => void patch({ enabled: e.target.checked })} />
        Afficher l’onglet Progrès et les célébrations
      </label>
      <label>
        Objectif du jour (tâches)
        <input type="number" min={1} max={20} value={cfg.daily_goal} onChange={(e) => e.target.value && void patch({ daily_goal: Number(e.target.value) })} />
      </label>
    </fieldset>
  )
}
