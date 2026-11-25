import { useEffect, useState } from 'react'
import { DetectionSection } from './DetectionSettings'

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [shortcut, setShortcut] = useState('')
  const [launchAtLogin, setLaunchAtLogin] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    void window.hark.getSettings().then((s) => {
      setShortcut(s.shortcut)
      setLaunchAtLogin(s.launchAtLogin)
    })
  }, [])

  async function save() {
    try {
      await window.hark.setSettings({ shortcut: shortcut.trim(), launchAtLogin })
      setMessage('Enregistré')
    } catch (err) {
      setMessage(String((err as Error).message).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''))
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Réglages" onMouseDown={onClose}>
      <div className="modal__panel modal__panel--small modal__panel--scroll" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Réglages</h2>
        <label>
          Raccourci global
          <input value={shortcut} onChange={(e) => setShortcut(e.target.value)} placeholder="Control+Alt+K" />
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={launchAtLogin} onChange={(e) => setLaunchAtLogin(e.target.checked)} />
          Lancer Hark au démarrage de la session
        </label>
        {message && <p className="modal__source">{message}</p>}
        <DetectionSection />
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
