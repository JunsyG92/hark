// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { validateApiRequest } from '../src/main/apiProxy'
import { AnalysisSection } from '../src/renderer/src/components/AnalysisSection'
import { MeetingsView } from '../src/renderer/src/components/MeetingsView'
import { TaskEditor } from '../src/renderer/src/components/TaskEditor'
import { createApi } from '../src/renderer/src/lib/api'
import { groupTasks } from '../src/renderer/src/lib/board'
import { analysisLabel } from '../src/renderer/src/lib/meetings'

afterEach(cleanup)

const meeting = (over: Record<string, unknown> = {}) => ({
  id: 'm1', title: 'Revue budget', status: 'recorded', app: '', started_at: '2026-11-25T10:00:00+00:00', ended_at: null,
  duration_ms: 600_000, tracks: ['system', 'mic'], audio_available: false, transcription: 'done', transcription_error: null,
  language: 'fr', task_count: 2, analysis: 'done', analysis_error: null, ...over,
})
const analysisDoc = {
  meeting_id: 'm1', title: 'Revue budget', summary: 'Point sur le budget.\nValidé avec réserve.', decisions: ['Budget Q1 validé'],
  open_questions: ['Qui valide l’enveloppe ?'], tasks_proposed: 2, provider: 'ollama', model: 'qwen2.5:7b-instruct', chunks: 1,
  tokens_in: 1200, tokens_out: 300, created_at: '2026-11-25T10:05:00+00:00',
}

function bridge(handlers: Record<string, unknown>) {
  const calls: string[] = []
  const api = vi.fn(async (req: { method: string; path: string; body?: unknown }) => {
    const key = `${req.method} ${req.path.split('?')[0]}`
    calls.push(`${req.method} ${req.path}`)
    const h = handlers[key]
    if (h === undefined) return { status: 200, body: [] }
    return { status: 200, body: typeof h === 'function' ? (h as (b: unknown) => unknown)(req.body) : h }
  })
  window.hark = { api, onMeetingsChanged: () => () => {}, saveFile: vi.fn() } as unknown as Window['hark']
  return { api, calls }
}

describe('analysis in the meeting detail', () => {
  it('shows summary, decisions, open questions and token usage; Ré-analyser forces', async () => {
    const { api, calls } = bridge({
      'GET /v1/meetings': [meeting()], 'GET /v1/meetings/m1/transcript': [], 'GET /v1/meetings/m1/analysis': analysisDoc,
    })
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} />))
    await act(async () => fireEvent.click(await screen.findByText('Revue budget')))
    expect(await screen.findByText(/Validé avec réserve/)).toBeTruthy()
    expect(screen.getByText('Budget Q1 validé')).toBeTruthy()
    expect(screen.getByText('Qui valide l’enveloppe ?')).toBeTruthy()
    expect(screen.getByText(/1500 tokens \(1 bloc\)/)).toBeTruthy()
    await act(async () => fireEvent.click(screen.getByText('Ré-analyser')))
    expect(calls).toContain('POST /v1/meetings/m1/analyze?force=true')
  })

  it('explains why the analysis is waiting', async () => {
    const { api } = bridge({
      'GET /v1/meetings': [meeting({ analysis: 'pending', analysis_error: 'llm_unavailable: Ollama injoignable sur http://127.0.0.1:11434' })],
      'GET /v1/meetings/m1/transcript': [],
    })
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} />))
    await act(async () => fireEvent.click(await screen.findByText('Revue budget')))
    expect(await screen.findByText(/Ollama injoignable/)).toBeTruthy()
    expect(analysisLabel({ transcription: 'done', analysis: 'pending', analysis_error: 'llm_unavailable: x' })).toBe('analyse en attente du LLM')
    expect(analysisLabel({ transcription: 'pending', analysis: 'none', analysis_error: null })).toBe('')
  })

  it('opens a meeting at the evidence timestamp when asked (task → source excerpt)', async () => {
    const { api } = bridge({
      'GET /v1/meetings': [meeting({ analysis: 'none' })],
      'GET /v1/meetings/m1/transcript': [
        { id: 1, meeting_id: 'm1', track: 'system', speaker: 'others', start_ms: 0, end_ms: 3000, text: 'Bonjour' },
        { id: 2, meeting_id: 'm1', track: 'mic', speaker: 'me', start_ms: 4000, end_ms: 7000, text: 'Je m’occupe du budget' },
      ],
    })
    await act(async () => void render(<MeetingsView api={createApi(api)} onError={() => {}} focusRequest={{ id: 'm1', ms: 4000, nonce: 1 }} />))
    const row = await screen.findByText('Je m’occupe du budget')
    expect(row.closest('li')!.className).toContain('transcript__row--focus')
  })
})

describe('tasks to validate', () => {
  const task = (id: string, mine: boolean, position: number) => ({
    id, title: id, description: '', assignee: '', due: null, priority: 'normal', column: 'to_validate', position, source: 'meeting:m1',
    evidence: { meeting_id: 'm1', start_ms: 4000, end_ms: 7000 }, is_mine: mine, confidence: 0.9, created_at: 'x', updated_at: 'x',
  })

  it('puts the user’s own tasks first in « À valider »', () => {
    const board = groupTasks([task('a', false, 0), task('b', true, 1), task('c', true, 2), task('d', false, 3)] as never)
    expect(board.to_validate.map((t) => t.id)).toEqual(['b', 'c', 'a', 'd'])
  })

  it('the editor links to the source excerpt', async () => {
    const open = vi.fn()
    render(<TaskEditor task={task('a', true, 0) as never} onSave={async () => {}} onDelete={async () => {}} onAccept={async () => {}} onClose={() => {}} onOpenEvidence={open} />)
    fireEvent.click(screen.getByText(/voir l’extrait à 00:04/))
    expect(open).toHaveBeenCalledWith('m1', 4000)
  })
})

describe('Analysis settings', () => {
  it('shows the Ollama status, recommended model, explicit pull, profile validation errors and a closed cloud block', async () => {
    const models = [
      { id: 'light', label: 'Léger', description: 'd1', ollama_model: 'qwen2.5:3b-instruct', download_gb: 1.9, min_ram_gb: 8, installed: false, recommended: false },
      { id: 'balanced', label: 'Équilibré', description: 'd2', ollama_model: 'qwen2.5:7b-instruct', download_gb: 4.7, min_ram_gb: 16, installed: true, recommended: true },
    ]
    const { api, calls } = bridge({
      'GET /v1/settings/llm': { provider: 'ollama', ollama_url: 'http://127.0.0.1:11434', model: 'qwen2.5:7b-instruct', chunk_tokens: 1500, max_tokens_per_meeting: 40000, auto_analyze: true },
      'GET /v1/llm/models': models,
      'GET /v1/analysis/status': { queue: [], current_meeting_id: null, provider: 'ollama', model: 'qwen2.5:7b-instruct', available: false, availability_error: 'Ollama injoignable', pull: { state: 'idle', model: null, error: null } },
      'POST /v1/llm/pull': { status: 'downloading' },
      'GET /v1/profile': { yaml: 'name: ""\n', profile: {}, error: null },
      'GET /v1/settings/cloud': { enabled: false, acknowledged: false, base_url: '', model: '', has_key: false },
    })
    const apiSave = api.getMockImplementation()!
    api.mockImplementation(async (req) => {
      if (req.method === 'PUT' && req.path === '/v1/profile') return { status: 422, body: { detail: 'unknown : Extra inputs are not permitted' } }
      return apiSave(req)
    })
    await act(async () => void render(<AnalysisSection />))
    expect((await screen.findByTestId('llm-status')).textContent).toContain('Ollama injoignable')
    expect(screen.getByText('recommandé pour cette machine')).toBeTruthy()
    expect(calls).not.toContain('POST /v1/llm/pull') // nothing downloads by itself
    await act(async () => fireEvent.click(screen.getByText('Télécharger')))
    expect(api).toHaveBeenCalledWith({ method: 'POST', path: '/v1/llm/pull', body: { model: 'qwen2.5:3b-instruct' } })
    await act(async () => fireEvent.change(screen.getByLabelText('Profil YAML'), { target: { value: 'unknown: 1' } }))
    await act(async () => fireEvent.click(screen.getByText('Enregistrer le profil')))
    expect(await screen.findByText(/Extra inputs are not permitted/)).toBeTruthy()
    const details = document.querySelector('details.cloud') as HTMLDetailsElement
    expect(details.open).toBe(false) // cloud is collapsed and off by default
    expect((screen.getByLabelText(/Utiliser le cloud/) as HTMLInputElement).disabled).toBe(true)
  })

  it('PUT is allowed through the API proxy, arbitrary methods are not', () => {
    expect(() => validateApiRequest({ method: 'PUT', path: '/v1/profile' })).not.toThrow()
    expect(() => validateApiRequest({ method: 'OPTIONS', path: '/v1/profile' })).toThrow()
    expect(() => validateApiRequest({ method: 'POST', path: `/v1/meetings/m1/analyze?force=true` })).not.toThrow()
    void waitFor
  })
})
