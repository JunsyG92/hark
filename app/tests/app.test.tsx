// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../src/renderer/src/App'
import type { Task } from '../src/renderer/src/lib/contracts.gen'

function fakeTask(over: Partial<Task>): Task {
  return {
    id: 'a', title: 'Préparer le budget Q1', description: '', assignee: 'Moi', due: null, priority: 'high',
    column: 'to_validate', position: 0, source: 'meeting:m1', evidence: null, is_mine: true, confidence: 0.8,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', ...over,
  }
}

function installBridge(tasks: Task[]) {
  const api = vi.fn(async (req: { method: string; path: string; body?: unknown }) => {
    if (req.path === '/v1/recording/status') return { status: 200, body: { recording: false, meeting_id: null, title: '', started_at: null, elapsed_s: 0, tracks: [], system_level_db: null, mic_level_db: null, silent_seconds: 0, silence_prompted: false, warnings: [] } }
    if (req.method === 'GET') return { status: 200, body: tasks }
    if (req.method === 'POST' && req.path === '/v1/tasks') {
      const t = fakeTask({ id: 'new', title: (req.body as { title: string }).title, column: 'todo', is_mine: false, source: 'manual' })
      tasks.push(t)
      return { status: 201, body: t }
    }
    return { status: 200, body: null }
  })
  window.hark = {
    api, getSettings: vi.fn(), setSettings: vi.fn(), hide: vi.fn(), onShown: () => () => {}, onTasksChanged: () => () => {}, onRecordingChanged: () => () => {}, platform: 'linux',
  } as unknown as Window['hark']
  return api
}

afterEach(cleanup)

describe('App', () => {
  it('renders the four columns and the proposed task', async () => {
    installBridge([fakeTask({})])
    await act(async () => render(<App />))
    for (const label of ['À valider', 'À faire', 'En cours', 'Fait']) expect(screen.getByRole('region', { name: label })).toBeTruthy()
    expect(screen.getByText('Préparer le budget Q1')).toBeTruthy()
    expect(screen.getByText('moi')).toBeTruthy()
  })

  it('creates a task via quick add', async () => {
    const api = installBridge([])
    await act(async () => render(<App />))
    const input = document.querySelector<HTMLInputElement>('[data-quick-add="todo"]')!
    fireEvent.change(input, { target: { value: 'Envoyer le CR' } })
    await act(async () => fireEvent.keyDown(input, { key: 'Enter' }))
    expect(api).toHaveBeenCalledWith({ method: 'POST', path: '/v1/tasks', body: { title: 'Envoyer le CR', column: 'todo' } })
    expect(await screen.findByText('Envoyer le CR')).toBeTruthy()
  })

  it('Escape hides the window', async () => {
    installBridge([])
    await act(async () => render(<App />))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(window.hark.hide).toHaveBeenCalled()
  })
})

describe('Detection settings', () => {
  it('shows live level, mic signal, and the test button sends a prompt request', async () => {
    const api = vi.fn(async (req: { method: string; path: string; body?: unknown }) => {
      if (req.path === '/v1/settings/detection' && req.method === 'GET')
        return { status: 200, body: { enabled: true, threshold_db: -45, min_seconds: 8, require_mic_in_use: true, prompt_seconds: 20, cooldown_ignore_minutes: 10, cooldown_decline_minutes: 30 } }
      if (req.path === '/v1/detection/status')
        return { status: 200, body: { phase: 'idle', level_db: -32.4, above_threshold_seconds: 3.5, mic_in_use: true, mic_apps: ['Teams'], audio_source: 'system-output-loopback', error: null, mic_probe: 'pactl', mic_probe_error: null, cooldown_remaining_s: 0, blockers: ['mic_not_in_use'] } }
      if (req.path === '/v1/settings/llm') return { status: 200, body: { provider: 'ollama', ollama_url: 'http://127.0.0.1:11434', model: 'qwen2.5:7b-instruct', chunk_tokens: 1500, max_tokens_per_meeting: 40000, auto_analyze: true } }
      if (req.path === '/v1/analysis/status') return { status: 200, body: { queue: [], current_meeting_id: null, provider: 'ollama', model: 'qwen2.5:7b-instruct', available: true, availability_error: null, pull: { state: 'idle', model: null, error: null } } }
      if (req.path === '/v1/profile') return { status: 200, body: { yaml: 'name: ""\n', profile: {}, error: null } }
      if (req.path === '/v1/settings/cloud') return { status: 200, body: { enabled: false, acknowledged: false, base_url: '', model: '', has_key: false } }
      if (req.path === '/v1/settings/transcription') return { status: 200, body: { profile: 'balanced', language: 'auto', auto_transcribe: true, retention_days: 0 } }
      if (req.path === '/v1/transcription/status') return { status: 200, body: { queue: [], current_meeting_id: null, progress: 0, model_installed: false, download: { state: 'idle', profile: null, error: null } } }
      if (req.path === '/v1/settings/recording') return { status: 200, body: { silence_minutes: 3, silence_threshold_db: -45 } }
      if (req.path === '/v1/recording/status') return { status: 200, body: { recording: false, meeting_id: null, title: '', started_at: null, elapsed_s: 0, tracks: [], system_level_db: null, mic_level_db: null, silent_seconds: 0, silence_prompted: false, warnings: [] } }
      if (req.path === '/v1/detection/test') return { status: 202, body: { prompted: true } }
      return { status: 200, body: [] }
    })
    window.hark = {
      api, getSettings: vi.fn(async () => ({ shortcut: 'Control+Alt+K', launchAtLogin: false })), setSettings: vi.fn(),
      hide: vi.fn(), onShown: () => () => {}, onTasksChanged: () => () => {}, onRecordingChanged: () => () => {}, platform: 'linux',
    } as unknown as Window['hark']
    const { SettingsPanel } = await import('../src/renderer/src/components/SettingsPanel')
    await act(async () => render(<SettingsPanel onClose={() => {}} />))
    expect(await screen.findByText(/Niveau : -32 dB/)).toBeTruthy()
    expect(screen.getByText(/oui \(Teams\)/)).toBeTruthy()
    expect(screen.getByTestId('blockers').textContent).toContain('Aucune application n’utilise le micro')
    await act(async () => fireEvent.click(screen.getByText('Tester la notification')))
    expect(api).toHaveBeenCalledWith({ method: 'POST', path: '/v1/detection/test', body: undefined })
    expect(await screen.findByText(/Notification de test envoyée/)).toBeTruthy()
  })
})
