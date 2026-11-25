// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { validateApiRequest } from '../src/main/apiProxy'
import { parseSaveRequest, sanitizeFileName } from '../src/main/files'
import { MeetingsView } from '../src/renderer/src/components/MeetingsView'
import { TranscriptionSection } from '../src/renderer/src/components/TranscriptionSection'
import { createApi } from '../src/renderer/src/lib/api'
import { displayTitle, durationLabel, enc, parseSnippet, timestamp, transcriptionLabel } from '../src/renderer/src/lib/meetings'

afterEach(cleanup)

const meeting = (over: Record<string, unknown> = {}) => ({
  id: 'm1', title: 'Revue budget', status: 'recorded', app: 'Teams', started_at: '2026-11-25T10:00:00+00:00', ended_at: null,
  duration_ms: 1_860_000, tracks: ['system', 'mic'], audio_available: false, transcription: 'done', transcription_error: null,
  language: 'fr', task_count: 2, ...over,
})
const seg = (id: number, speaker: string, start_ms: number, text: string) => ({ id, meeting_id: 'm1', track: speaker === 'me' ? 'mic' : 'system', speaker, start_ms, end_ms: start_ms + 3000, text })

function bridge(handlers: Record<string, unknown>) {
  const calls: string[] = []
  const api = vi.fn(async (req: { method: string; path: string; body?: unknown }) => {
    const key = `${req.method} ${req.path.split('?')[0]}`
    calls.push(`${req.method} ${req.path}`)
    const h = handlers[key]
    return { status: 200, body: typeof h === 'function' ? (h as (b: unknown) => unknown)(req.body) : (h ?? []) }
  })
  window.hark = { api, onMeetingsChanged: () => () => {}, saveFile: vi.fn(async () => ({ saved: true })) } as unknown as Window['hark']
  return { api, calls }
}

describe('meetings helpers', () => {
  it('formats titles, durations, timestamps, statuses', () => {
    expect(displayTitle({ title: ' Revue ', started_at: '2026-11-25T10:00:00Z' })).toBe('Revue')
    expect(displayTitle({ title: '', started_at: '2026-11-25T10:00:00Z' })).toMatch(/^Réunion du 25\/11\/2026/)
    expect(durationLabel(1_860_000)).toBe('31 min')
    expect(durationLabel(5_400_000)).toBe('1 h 30')
    expect(durationLabel(null)).toBe('—')
    expect(timestamp(3_725_000)).toBe('1:02:05')
    expect(timestamp(65_000)).toBe('01:05')
    expect(transcriptionLabel({ status: 'recorded', transcription: 'pending', transcription_error: 'model_not_installed' })).toContain('modèle')
  })

  it('renders only <mark> from snippets (no HTML injection)', () => {
    expect(parseSnippet('le <mark>budget</mark> Q1 <img src=x onerror=alert(1)>')).toEqual([
      { text: 'le ', match: false }, { text: 'budget', match: true }, { text: ' Q1 <img src=x onerror=alert(1)>', match: false },
    ])
    expect(enc("l'été (Q1)*")).not.toMatch(/['()*]/)
  })
})

describe('api whitelist for the new routes', () => {
  it('accepts export.md and encoded search, rejects traversal', () => {
    expect(() => validateApiRequest({ method: 'GET', path: '/v1/meetings/abc/export.md' })).not.toThrow()
    expect(() => validateApiRequest({ method: 'GET', path: `/v1/search?q=${enc("budget Q1 l'été")}&limit=40` })).not.toThrow()
    expect(() => validateApiRequest({ method: 'GET', path: '/v1/meetings/../x' })).toThrow()
  })

  it('save requests are sanitized and size-limited', () => {
    expect(sanitizeFileName('Revue/budget: Q1?')).toBe('Revue_budget_ Q1_.md')
    expect(sanitizeFileName('..')).toBe('reunion.md')
    expect(parseSaveRequest({ suggestedName: 'a.md', content: '# x' })).toEqual({ fileName: 'a.md', content: '# x' })
    expect(parseSaveRequest({ suggestedName: 'a', content: 5 })).toBeNull()
    expect(parseSaveRequest({ suggestedName: 'a', content: 'x'.repeat(21 * 1024 * 1024) })).toBeNull()
  })
})

describe('MeetingsView', () => {
  it('lists meetings, opens the timestamped transcript and exports Markdown', async () => {
    const { api, calls } = bridge({
      'GET /v1/meetings': [meeting(), meeting({ id: 'm2', title: '', transcription: 'pending', transcription_error: 'model_not_installed', task_count: 0 })],
      'GET /v1/meetings/m1/transcript': [seg(1, 'others', 0, 'Bonjour à tous'), seg(2, 'me', 4000, 'Je m’occupe du budget')],
      'GET /v1/tasks': [{ id: 't', title: 'Envoyer le budget', column: 'to_validate' }],
      'GET /v1/meetings/m1/export.md': '# Revue budget\n',
    })
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} />))
    expect(await screen.findByText('Revue budget')).toBeTruthy()
    expect(screen.getByText(/2 tâches/)).toBeTruthy()
    expect(screen.getByText('en attente d’un modèle')).toBeTruthy()
    await act(async () => fireEvent.click(screen.getByText('Revue budget')))
    expect(await screen.findByText('Bonjour à tous')).toBeTruthy()
    expect(screen.getByText('Moi')).toBeTruthy()
    expect(screen.getByText('Autres')).toBeTruthy()
    expect(screen.getByText('Envoyer le budget')).toBeTruthy()
    await act(async () => fireEvent.click(screen.getByText('Exporter en Markdown')))
    expect(window.hark.saveFile).toHaveBeenCalledWith(expect.stringContaining('Revue budget'), '# Revue budget\n')
    expect(calls).toContain('GET /v1/meetings/m1/export.md')
  })

  it('searches with debounce and shows highlighted matches', async () => {
    const { api, calls } = bridge({
      'GET /v1/meetings': [meeting()],
      'GET /v1/search': [{ meeting_id: 'm1', meeting_title: 'Revue budget', kind: 'transcript', snippet: 'le <mark>budget</mark> Q1', start_ms: 65000, speaker: 'others' }],
    })
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} />))
    fireEvent.change(screen.getByLabelText('Rechercher dans les réunions'), { target: { value: 'budget Q1' } })
    const mark = await waitFor(() => {
      const el = document.querySelector('mark')
      if (!el) throw new Error('no mark yet')
      return el
    })
    expect(mark.textContent).toBe('budget')
    expect(screen.getByText(/01:05/)).toBeTruthy()
    expect(calls.some((c) => c.startsWith('GET /v1/search?q=budget%20Q1'))).toBe(true)
  })

  it('delete asks for confirmation first', async () => {
    const { api, calls } = bridge({ 'GET /v1/meetings': [meeting()], 'GET /v1/meetings/m1/transcript': [] })
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} />))
    await act(async () => fireEvent.click(await screen.findByText('Revue budget')))
    await act(async () => fireEvent.click(await screen.findByText('Supprimer')))
    expect(calls).not.toContain('DELETE /v1/meetings/m1')
    await act(async () => fireEvent.click(screen.getByText('Supprimer')))
    await waitFor(() => expect(calls).toContain('DELETE /v1/meetings/m1'))
  })
})

describe('TranscriptionSection', () => {
  it('shows profiles with the recommended one, explicit download, and retention choices', async () => {
    const models = [
      { id: 'light', label: 'Léger', description: 'd1', whisper_model: 'base', download_mb: 150, min_ram_gb: 4, gpu_recommended: false, installed: true, recommended: false },
      { id: 'balanced', label: 'Équilibré', description: 'd2', whisper_model: 'small', download_mb: 490, min_ram_gb: 8, gpu_recommended: false, installed: false, recommended: true },
    ]
    const { api, calls } = bridge({
      'GET /v1/models': models,
      'GET /v1/settings/transcription': { profile: 'balanced', language: 'auto', auto_transcribe: true, retention_days: 0 },
      'GET /v1/transcription/status': { queue: [], current_meeting_id: null, progress: 0, model_installed: false, download: { state: 'idle', profile: null, error: null } },
      'PATCH /v1/settings/transcription': (b: unknown) => ({ profile: 'balanced', language: 'auto', auto_transcribe: true, retention_days: 0, ...(b as object) }),
      'POST /v1/models/download': { status: 'downloading' },
    })
    await act(async () => void render(<TranscriptionSection />))
    expect(await screen.findByText('recommandé pour cette machine')).toBeTruthy()
    expect(screen.getByText('installé ✓')).toBeTruthy()
    expect(calls).not.toContain('POST /v1/models/download') // nothing downloads by itself
    await act(async () => fireEvent.click(screen.getByText('Télécharger')))
    expect(api).toHaveBeenCalledWith({ method: 'POST', path: '/v1/models/download', body: { profile: 'balanced' } })
    await act(async () => fireEvent.change(screen.getByLabelText('Audio après transcription'), { target: { value: '30' } }))
    expect(api).toHaveBeenCalledWith({ method: 'PATCH', path: '/v1/settings/transcription', body: { retention_days: 30 } })
  })
})
