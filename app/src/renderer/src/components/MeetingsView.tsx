import { useCallback, useEffect, useRef, useState } from 'react'
import type { Analysis, HarkApi, Meeting, SearchHit, Task, TranscriptSegment } from '../lib/api'
import { COLUMNS } from '../lib/board'
import {
  analysisLabel, displayTitle, durationLabel, formatDateTime, parseSnippet, timestamp, transcriptionLabel,
} from '../lib/meetings'

const SPEAKER = { me: 'Moi', others: 'Autres' } as const

function Snippet({ text }: { text: string }) {
  return (
    <>
      {parseSnippet(text).map((p, i) =>
        p.match ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>,
      )}
    </>
  )
}

export interface FocusRequest {
  id: string
  ms: number
  nonce: number
}

export function MeetingsView({
  api, onError, focusRequest,
}: {
  api: HarkApi
  onError: (msg: string | null) => void
  focusRequest?: FocusRequest | null
}) {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [selected, setSelected] = useState<{ id: string; focusMs: number | null } | null>(null)

  const reload = useCallback(async () => {
    try {
      setMeetings(await api.listMeetings())
    } catch (err) {
      onError(`Moteur injoignable : ${(err as Error).message}`)
    }
  }, [api, onError])

  useEffect(() => {
    void reload()
    const off = window.hark.onMeetingsChanged(() => void reload())
    return off
  }, [reload])

  // Keep the list fresh while something is being processed.
  const busy = meetings.some(
    (m) => m.status === 'recording' || ['running', 'pending'].includes(m.transcription) || ['running', 'pending'].includes(m.analysis),
  )
  useEffect(() => {
    if (!busy) return
    const id = window.setInterval(() => document.visibilityState === 'visible' && void reload(), 3000)
    return () => window.clearInterval(id)
  }, [busy, reload])

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) return setHits(null)
    const timer = window.setTimeout(() => {
      api.search(q).then(setHits).catch(() => setHits([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [api, query])

  useEffect(() => {
    if (focusRequest) setSelected({ id: focusRequest.id, focusMs: focusRequest.ms })
  }, [focusRequest])

  const current = selected ? meetings.find((m) => m.id === selected.id) : undefined

  if (current && selected) {
    return (
      <div className="meetings meetings--detail">
        <button className="detail__back chip" onClick={() => setSelected(null)}>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 4L6 8l4 4" /></svg>
          Réunions
        </button>
        <MeetingDetail key={current.id} api={api} meeting={current} focusMs={selected.focusMs} onChanged={reload} onGone={() => setSelected(null)} onError={onError} />
      </div>
    )
  }

  return (
    <div className="meetings">
      <div className="search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>
        <input
          className="meetings__search"
          type="search"
          placeholder="Rechercher dans les réunions…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Rechercher dans les réunions"
        />
        <span className="search__count">{hits !== null ? `${hits.length} résultat${hits.length > 1 ? 's' : ''}` : `${meetings.length} réunion${meetings.length > 1 ? 's' : ''}`}</span>
      </div>
      {hits !== null ? (
        <ul className="meetings__list" aria-label="Résultats">
          {hits.length === 0 && <li className="meetings__empty">Aucun résultat.</li>}
          {hits.map((h, i) => (
            <li key={`${h.meeting_id}-${h.start_ms}-${i}`}>
              <button className="meeting-row" onClick={() => setSelected({ id: h.meeting_id, focusMs: h.start_ms })}>
                <span className="meeting-row__title">{h.meeting_title || 'Réunion sans titre'}</span>
                <span className="meeting-row__time">
                  {h.kind === 'title' ? 'titre' : h.kind === 'summary' ? 'résumé' : `${h.start_ms !== null ? timestamp(h.start_ms) : ''} ${h.speaker ? SPEAKER[h.speaker] : ''}`}
                </span>
                <span className="meeting-row__snippet"><Snippet text={h.snippet} /></span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="meetings__list" aria-label="Réunions">
          {meetings.length === 0 && (
            <li className="meetings__empty">
              <b>Aucune réunion pour l’instant</b>
              Clique sur « ● Enregistrer » pendant une réunion.
            </li>
          )}
          {meetings.map((m) => (
            <li key={m.id}>
              <button className="meeting-row" onClick={() => setSelected({ id: m.id, focusMs: null })}>
                <span className="meeting-row__title">{displayTitle(m)}</span>
                <span className="meeting-row__time">{formatDateTime(m.started_at)}</span>
                <span className="meeting-row__meta">
                  <i className={`dot dot--${m.analysis === 'done' ? 'ok' : m.transcription === 'failed' || m.analysis === 'failed' ? 'err' : 'wait'}`} />
                  {durationLabel(m.duration_ms)} · {m.task_count} tâche{m.task_count > 1 ? 's' : ''} ·{' '}
                  <span className={`meeting-row__status meeting-row__status--${m.transcription}`}>
                    {transcriptionLabel(m)}{analysisLabel(m) ? ` · ${analysisLabel(m)}` : ''}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MeetingDetail({
  api, meeting, focusMs, onChanged, onGone, onError,
}: {
  api: HarkApi
  meeting: Meeting
  focusMs: number | null
  onChanged: () => Promise<void>
  onGone: () => void
  onError: (msg: string | null) => void
}) {
  const [segments, setSegments] = useState<TranscriptSegment[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [steps, setSteps] = useState<{ step: number; steps: number; model: string } | null>(null)
  const [title, setTitle] = useState(meeting.title)
  const focusRef = useRef<HTMLLIElement | null>(null)

  useEffect(() => {
    let alive = true
    void api.transcript(meeting.id).then((s) => alive && setSegments(s)).catch(() => undefined)
    void api.meetingTasks(meeting.id).then((t) => alive && setTasks(t)).catch(() => undefined)
    if (meeting.analysis === 'done') void api.analysis(meeting.id).then((a) => alive && setAnalysis(a)).catch(() => alive && setAnalysis(null))
    else setAnalysis(null)
    return () => {
      alive = false
    }
  }, [api, meeting.id, meeting.transcription, meeting.analysis])

  // While the LLM works (can take minutes locally), show where it is.
  useEffect(() => {
    if (meeting.analysis !== 'running') return setSteps(null)
    let alive = true
    const tick = () =>
      void api.analysisStatus().then((s) => {
        if (alive && s.current_meeting_id === meeting.id) setSteps({ step: s.step, steps: s.steps, model: s.model })
      }).catch(() => undefined)
    tick()
    const id = window.setInterval(tick, 2000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [api, meeting.id, meeting.analysis])

  useEffect(() => {
    focusRef.current?.scrollIntoView?.({ block: 'center' })
  }, [segments, focusMs])

  const focused = focusMs === null ? null : segments.find((s) => s.start_ms <= focusMs && focusMs <= s.end_ms) ?? segments.find((s) => s.start_ms === focusMs) ?? null

  async function saveTitle() {
    if (title.trim() === meeting.title) return
    try {
      await api.renameMeeting(meeting.id, title.trim())
      await onChanged()
    } catch (err) {
      onError((err as Error).message)
    }
  }

  async function exportMd() {
    try {
      const md = await api.exportMarkdown(meeting.id)
      await window.hark.saveFile(displayTitle(meeting), md)
    } catch (err) {
      onError(`Export impossible : ${(err as Error).message}`)
    }
  }

  async function remove() {
    const ok = await window.hark.confirm({ message: 'Supprimer cette réunion ?', detail: 'Sa transcription, son analyse et son audio seront supprimés. Cette action est définitive.', confirmLabel: 'Supprimer' })
    if (!ok) return
    try {
      await api.deleteMeeting(meeting.id)
      onGone()
      await onChanged()
    } catch (err) {
      onError((err as Error).message)
    }
  }

  async function analyze(force: boolean) {
    try {
      await api.analyze(meeting.id, force)
      await onChanged()
    } catch (err) {
      onError((err as Error).message)
    }
  }

  async function retry() {
    try {
      await api.retranscribe(meeting.id)
      await onChanged()
    } catch (err) {
      onError((err as Error).message)
    }
  }

  const waitingModel = meeting.transcription === 'pending' && meeting.transcription_error === 'model_not_installed'
  return (
    <div className="detail">
      <input className="detail__title" value={title} placeholder={displayTitle(meeting)} maxLength={200} onChange={(e) => setTitle(e.target.value)} onBlur={() => void saveTitle()} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} aria-label="Titre de la réunion" />
      <p className="detail__meta">
        {formatDateTime(meeting.started_at)} · {durationLabel(meeting.duration_ms)}
        {meeting.language ? ` · ${meeting.language}` : ''}
        {meeting.app ? ` · ${meeting.app}` : ''} · {transcriptionLabel(meeting)}
        {analysisLabel(meeting) ? ` · ${analysisLabel(meeting)}` : ''}
      </p>
      {waitingModel && <p className="banner banner--info">Aucun modèle de transcription installé : ouvre Réglages → Transcription et télécharge-en un. L’audio est conservé en attendant.</p>}
      {meeting.analysis === 'pending' && meeting.analysis_error?.startsWith('llm_unavailable') && (
        <p className="banner banner--info">Analyse en attente : {meeting.analysis_error.replace('llm_unavailable: ', '')} (Réglages → Analyse IA).</p>
      )}
      {meeting.analysis === 'running' && (
        <p className="banner banner--info" role="status">
          Analyse en cours{steps && steps.steps > 0 ? ` : étape ${Math.min(steps.step + 1, steps.steps)}/${steps.steps}` : '…'}
          {steps?.model ? ` (${steps.model})` : ''}. Avec un modèle local, cela peut prendre plusieurs minutes ; les tâches
          arriveront dans « À valider ».
        </p>
      )}
      {meeting.analysis === 'pending' && !meeting.analysis_error && (
        <p className="banner banner--info" role="status">Analyse en file d’attente…</p>
      )}
      {meeting.analysis === 'failed' && <p className="banner">L’analyse a échoué ({meeting.analysis_error}).</p>}
      {meeting.transcription === 'failed' && <p className="banner">La transcription a échoué ({meeting.transcription_error}). L’audio est conservé.</p>}
      <div className="detail__actions">
        <button className="btn" onClick={() => void exportMd()} disabled={segments.length === 0}>Exporter en Markdown</button>
        {meeting.audio_available && meeting.status === 'recorded' && meeting.transcription !== 'running' && (
          <button className="btn" onClick={() => void retry()}>{meeting.transcription === 'done' ? 'Retranscrire' : 'Transcrire'}</button>
        )}
        {meeting.transcription === 'done' && (
          <button
            className="btn"
            disabled={meeting.analysis === 'running'}
            onClick={() => void analyze(meeting.analysis === 'done')}
            title={meeting.analysis === 'done' ? 'Relance l’IA même si rien n’a changé (consomme des tokens)' : undefined}
          >
            {meeting.analysis === 'running' ? 'Analyse en cours…' : meeting.analysis === 'done' ? 'Ré-analyser' : 'Analyser'}
          </button>
        )}
        <span className="spacer" />
        <button className="btn btn--danger" onClick={() => void remove()}>Supprimer</button>
      </div>
      {analysis && (
        <div className="detail__analysis">
          <h3>Résumé</h3>
          <p className="detail__summary">{analysis.summary}</p>
          {analysis.decisions.length > 0 && (<><h3>Décisions</h3><ul>{analysis.decisions.map((d) => <li key={d}>{d}</li>)}</ul></>)}
          {analysis.open_questions.length > 0 && (<><h3>Questions ouvertes</h3><ul>{analysis.open_questions.map((q) => <li key={q}>{q}</li>)}</ul></>)}
          <p className="detail__meta">
            {analysis.tasks_proposed} tâche{analysis.tasks_proposed > 1 ? 's' : ''} proposée{analysis.tasks_proposed > 1 ? 's' : ''} dans « À valider » · {analysis.model} · {analysis.tokens_in + analysis.tokens_out} tokens ({analysis.chunks} bloc{analysis.chunks > 1 ? 's' : ''})
          </p>
        </div>
      )}
      {tasks.length > 0 && (
        <div className="detail__tasks">
          <h3>Tâches liées</h3>
          <ul>
            {tasks.map((t) => (
              <li key={t.id}>{t.title} <span className="pill">{COLUMNS.find((c) => c.id === t.column)?.label}</span></li>
            ))}
          </ul>
        </div>
      )}
      <h3>Transcription</h3>
      {segments.length === 0 ? (
        <p className="meetings__empty">Pas encore de transcription.</p>
      ) : (
        <ol className="transcript">
          {segments.map((s) => (
            <li key={s.id} ref={focused?.id === s.id ? focusRef : undefined} className={`transcript__row${focused?.id === s.id ? ' transcript__row--focus' : ''}`}>
              <span className="transcript__ts">{timestamp(s.start_ms)}</span>
              <span className={`pill pill--${s.speaker}`}>{SPEAKER[s.speaker]}</span>
              <span>{s.text}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
