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
      <div className="recbar recbar--on" role="status">
        <span className="recbar__dot" aria-hidden="true" />
        <strong>REC</strong>
        <span className="recbar__time">{formatDuration(status.elapsed_s)}</span>
        {status.warnings.length > 0 && <span className="recbar__warn" title={status.warnings.join('\n')}>⚠</span>}
        <button className="btn recbar__stop" onClick={() => void stop()}>
          ■ Stop
        </button>
      </div>
    )
  }
  return (
    <div className="recbar">
      {reminder && <span className="recbar__hint" role="status">Pense à informer les participants.</span>}
      <button className="btn" data-testid="rec-button" onClick={() => void start()}>
        ● Enregistrer
      </button>
    </div>
  )
}
