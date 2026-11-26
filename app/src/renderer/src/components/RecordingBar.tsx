import { useCallback, useEffect, useState } from 'react'
import type { HarkApi, RecordingStatus } from '../lib/api'
import { formatDuration } from '../lib/recording'

/** Start/Stop control, always visible in the top bar. Starting is always an explicit click. */
export function RecordingBar({ api, onError }: { api: HarkApi; onError: (msg: string | null) => void }) {
  const [status, setStatus] = useState<RecordingStatus | null>(null)
  const [reminder, setReminder] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.recordingStatus())
    } catch {
      /* engine not reachable: the main banner already says so */
    }
  }, [api])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void refresh()
    }, 1000)
    const off = window.hark.onRecordingChanged(() => void refresh())
    return () => {
      window.clearInterval(id)
      off()
    }
  }, [refresh])

  async function start() {
    try {
      await api.startRecording()
      onError(null)
      setReminder(true)
      window.setTimeout(() => setReminder(false), 6000)
    } catch (err) {
      onError(`Impossible de démarrer l’enregistrement : ${(err as Error).message}`)
    }
    await refresh()
  }

  async function stop() {
    try {
      await api.stopRecording()
    } catch (err) {
      onError((err as Error).message)
    }
    setReminder(false)
    await refresh()
  }

  if (status?.recording) {
    return (
      <div className="recbar recbar--on" role="status" aria-label={`Enregistrement en cours : ${formatDuration(status.elapsed_s)}`}>
        <span className="recbar__dot" aria-hidden="true" />
        <span className="recbar__time">{formatDuration(status.elapsed_s)}</span>
        {status.warnings.length > 0 && <span className="recbar__warn" title={status.warnings.join('\n')}>⚠</span>}
        <button className="icon-btn recbar__stop" title="Arrêter l’enregistrement" aria-label="Arrêter l’enregistrement" onClick={() => void stop()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" /></svg>
        </button>
      </div>
    )
  }
  return (
    <div className="recbar">
      {reminder && <span className="recbar__hint" role="status">Pense à informer les participants.</span>}
      <button className="icon-btn recbar__start" data-testid="rec-button" title="Enregistrer cette réunion" aria-label="Enregistrer" onClick={() => void start()}>
        <span className="recbar__dot recbar__dot--idle" aria-hidden="true" />
      </button>
    </div>
  )
}
