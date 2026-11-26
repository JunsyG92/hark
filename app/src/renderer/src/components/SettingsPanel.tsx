import { useEffect, useState } from 'react'
import { AnalysisSection } from './AnalysisSection'
import { DetectionSection } from './DetectionSettings'
import { RecordingSection } from './RecordingSection'
import { ProgressSection } from './ProgressSection'
import { TeamSection } from './TeamSection'
import { TranscriptionSection } from './TranscriptionSection'

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [shortcut, setShortcut] = useState('')
  const [launchAtLogin, setLaunchAtLogin] = useState(false)
  const [hideOnBlur, setHideOnBlur] = useState(true)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    void window.hark.getSettings().then((s) => {
      setShortcut(s.shortcut)
      setLaunchAtLogin(s.launchAtLogin)
      setHideOnBlur(s.hideOnBlur ?? true)
    })
  }, [])

  async function save() {
    try {
      await window.hark.setSettings({ shortcut: shortcut.trim(), launchAtLogin, hideOnBlur })
      setMessage('Enregistré')
    } catch (err) {
      setMessage(String((err as Error).message).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''))
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Réglages" onMouseDown={onClose}>
      <div className="modal__panel modal__panel--wide modal__panel--scroll" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Réglages</h2>
        <label>
          Raccourci global
          <input value={shortcut} onChange={(e) => setShortcut(e.target.value)} placeholder="Control+Alt+K" />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={launchAtLogin} onChange={(e) => setLaunchAtLogin(e.target.checked)} />
          Lancer Hark au démarrage de la session
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={hideOnBlur} onChange={(e) => setHideOnBlur(e.target.checked)} />
          Masquer le panneau quand je clique ailleurs (sinon il reste épinglé)
        </label>
        {message && <p className="modal__source">{message}</p>}
        <TeamSection />
        <ProgressSection />
        <DetectionSection />
        <RecordingSection />
        <TranscriptionSection />
        <AnalysisSection />
        <div className="modal__actions">
          <span className="spacer" />
          <button className="btn btn--ghost" onClick={onClose}>
            Fermer
          </button>
          <button className="btn btn--primary" onClick={() => void save()}>
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  )
}
