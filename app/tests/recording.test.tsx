// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  allowedActions, endedPayload, parseRecordingStarted, parseSilence, parseTitle, parseToastResponse,
} from '../src/main/detection'
import { RecordingBar } from '../src/renderer/src/components/RecordingBar'
import { createApi } from '../src/renderer/src/lib/api'
import { formatDuration } from '../src/renderer/src/lib/recording'
import { initOverlay, formatElapsed, type OverlayState } from '../src/renderer/src/overlay'
import { initToast, type Prompt } from '../src/renderer/src/toast'

afterEach(() => {
  cleanup()
  document.body.innerHTML = ''
})

const TOAST_DOM = `<main><h1 id="t-title"></h1><p id="t-text"></p><p id="t-reminder"></p>
<button id="b-primary"></button><button id="b-secondary"></button><div id="t-bar"></div></main>`

function setupToast() {
  document.body.innerHTML = TOAST_DOM
  let show: (p: Prompt) => void = () => undefined
  const respond = vi.fn()
  initToast(document, { onPrompt: (cb) => (show = cb), respond })
  return { show: (p: Prompt) => act(() => show(p)), respond }
}

describe('toast', () => {
  it('consent: Enregistrer / Non / Escape and the consent reminder', () => {
    const t = setupToast()
    t.show({ kind: 'consent', promptId: 'p1', app: 'Teams', promptSeconds: 20, silenceMinutes: 0, reminder: 'Pense à informer les participants.' })
    expect(document.getElementById('t-text')!.textContent).toContain('Teams')
    expect(document.getElementById('t-reminder')!.textContent).toContain('informer les participants')
    fireEvent.click(document.getElementById('b-primary')!)
    expect(t.respond).toHaveBeenCalledWith('p1', 'record')
    t.show({ kind: 'consent', promptId: 'p2', app: '', promptSeconds: 20, silenceMinutes: 0, reminder: '' })
    fireEvent.click(document.getElementById('b-secondary')!)
    expect(t.respond).toHaveBeenLastCalledWith('p2', 'decline')
    t.show({ kind: 'consent', promptId: 'p3', app: '', promptSeconds: 20, silenceMinutes: 0, reminder: '' })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(t.respond).toHaveBeenLastCalledWith('p3', 'ignore')
  })

  it('consent: no answer within the delay counts as ignore, and an answer is sent only once', () => {
    vi.useFakeTimers()
    const t = setupToast()
    t.show({ kind: 'consent', promptId: 'p1', app: '', promptSeconds: 5, silenceMinutes: 0, reminder: '' })
    vi.advanceTimersByTime(5100)
    expect(t.respond).toHaveBeenCalledWith('p1', 'ignore')
    fireEvent.click(document.getElementById('b-primary')!)
    expect(t.respond).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('"Réunion terminée ?" stays (no timeout) and offers Arrêter / Continuer', () => {
    vi.useFakeTimers()
    const t = setupToast()
    t.show({ kind: 'ended', promptId: 'm1', app: '', promptSeconds: 0, silenceMinutes: 3, reminder: '' })
    expect(document.getElementById('t-title')!.textContent).toBe('Réunion terminée ?')
    expect(document.getElementById('t-text')!.textContent).toContain('3 min')
    vi.advanceTimersByTime(10 * 60 * 1000)
    expect(t.respond).not.toHaveBeenCalled()
    fireEvent.click(document.getElementById('b-primary')!)
    expect(t.respond).toHaveBeenCalledWith('m1', 'stop')
    t.show({ kind: 'ended', promptId: 'm1', app: '', promptSeconds: 0, silenceMinutes: 3, reminder: '' })
    fireEvent.click(document.getElementById('b-secondary')!)
    expect(t.respond).toHaveBeenLastCalledWith('m1', 'continue')
    vi.useRealTimers()
  })
})

describe('overlay', () => {
  it('shows elapsed time, sends the title once, and Stop', () => {
    document.body.innerHTML = `<span id="o-time"></span><input id="o-title"><button id="o-stop"></button>`
    let push: (s: OverlayState) => void = () => undefined
    const bridge = { onState: (cb: (s: OverlayState) => void) => (push = cb), stop: vi.fn(), setTitle: vi.fn() }
    initOverlay(document, bridge, () => 65_000)
    act(() => push({ meetingId: 'm', startedAtMs: 0, title: '' }))
    expect(document.getElementById('o-time')!.textContent).toBe('01:05')
    const input = document.getElementById('o-title') as HTMLInputElement
    fireEvent.change(input, { target: { value: '  Revue budget ' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.blur(input)
    expect(bridge.setTitle).toHaveBeenCalledTimes(1)
    expect(bridge.setTitle).toHaveBeenCalledWith('Revue budget')
    fireEvent.click(document.getElementById('o-stop')!)
    expect(bridge.stop).toHaveBeenCalled()
    expect(formatElapsed(3_725_000)).toBe('1:02:05')
  })
})

describe('recording bar', () => {
  function bridge(status: Record<string, unknown>) {
    const calls: string[] = []
    const api = vi.fn(async (req: { method: string; path: string }) => {
      calls.push(`${req.method} ${req.path}`)
      if (req.path === '/v1/recording/status') return { status: 200, body: status }
      return { status: 201, body: {} }
    })
    window.hark = { api, onRecordingChanged: () => () => {} } as unknown as Window['hark']
    return { api, calls }
  }
  const idle = { recording: false, elapsed_s: 0, warnings: [] }

  it('starting is an explicit click and shows the consent reminder', async () => {
    const { api, calls } = bridge(idle)
    await act(async () => void render(<RecordingBar api={createApi(api)} onError={() => {}} />))
    expect(calls).not.toContain('POST /v1/recording/start')
    await act(async () => fireEvent.click(screen.getByTestId('rec-button')))
    expect(calls).toContain('POST /v1/recording/start')
    expect(screen.getByText(/informer les participants/)).toBeTruthy()
  })

  it('while recording: REC indicator, elapsed time and an always-available Stop', async () => {
    const { api, calls } = bridge({ recording: true, elapsed_s: 125, warnings: ['mic: no microphone found'] })
    await act(async () => void render(<RecordingBar api={createApi(api)} onError={() => {}} />))
    expect(screen.getByText('REC')).toBeTruthy()
    expect(screen.getByText('02:05')).toBeTruthy()
    await act(async () => fireEvent.click(screen.getByText('■ Stop')))
    expect(calls).toContain('POST /v1/recording/stop')
  })
})

describe('main-process boundaries', () => {
  it('only accepts answers valid for the toast kind', () => {
    expect(allowedActions('consent')).toEqual(['record', 'decline', 'ignore'])
    expect(allowedActions('ended')).toEqual(['stop', 'continue'])
    expect(parseToastResponse({ promptId: 'm', action: 'stop' })).toEqual({ promptId: 'm', action: 'stop' })
    expect(parseToastResponse({ promptId: 'm', action: 'rm -rf' })).toBeNull()
  })

  it('parses silence and recording events, rejecting malformed data', () => {
    expect(parseSilence({ meeting_id: 'm', silent: true, silence_seconds: 181 })).toEqual({ meetingId: 'm', silent: true, silenceSeconds: 181 })
    expect(parseSilence({ meeting_id: 'm', silent: 'yes' })).toBeNull()
    expect(endedPayload({ meetingId: 'm', silent: true, silenceSeconds: 181 })).toMatchObject({ kind: 'ended', silenceMinutes: 3, promptSeconds: 0 })
    expect(parseRecordingStarted({ meeting: { id: 'm', started_at: '2026-11-25T10:00:00+00:00', title: 'x' } })).toMatchObject({ meetingId: 'm', title: 'x' })
    expect(parseRecordingStarted({ meeting: { id: 'm', started_at: 'garbage' } })).toBeNull()
    expect(parseRecordingStarted({})).toBeNull()
    expect(parseTitle('  Revue ')).toBe('Revue')
    expect(parseTitle('x'.repeat(201))).toBeNull()
    expect(parseTitle(42)).toBeNull()
    expect(formatDuration(3725)).toBe('1:02:05')
  })
})
