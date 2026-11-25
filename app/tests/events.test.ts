import { describe, expect, it, vi } from 'vitest'
import { parseDetected, parseToastResponse } from '../src/main/detection'
import { EngineEvents, createSseParser, type SseMessage } from '../src/main/events'
import { dbToPercent, micLabel } from '../src/renderer/src/lib/detection'

function parse(chunks: string[]): SseMessage[] {
  const out: SseMessage[] = []
  const feed = createSseParser((m) => out.push(m))
  chunks.forEach(feed)
  return out
}

describe('sse parser', () => {
  it('parses events split across arbitrary chunks and ignores comments', () => {
    const msgs = parse([': connected\n\nid: 1\nev', 'ent: meeting.detected\ndata: {"a"', ':1}\n\n', ': ping\n\n'])
    expect(msgs).toEqual([{ event: 'meeting.detected', data: '{"a":1}', id: '1' }])
  })

  it('handles CRLF and multi-line data', () => {
    expect(parse(['event: x\r\ndata: a\r\ndata: b\r\n\r\n'])).toEqual([{ event: 'x', data: 'a\nb', id: undefined }])
  })
})

describe('event client', () => {
  it('dispatches valid events and drops malformed ones', async () => {
    const body = new Response(
      ': connected\n\nevent: task.updated\ndata: {"id":"1","type":"task.updated","occurred_at":"x","data":{}}\n\nevent: x\ndata: not json\n\n',
    ).body
    const seen: string[] = []
    let calls = 0
    const fetchImpl = vi.fn(async () => {
      calls += 1
      if (calls > 1) await new Promise(() => undefined) // second connection stays open
      return new Response(body, { status: 200 })
    })
    const client = new EngineEvents(
      async () => ({ port: 1, token: 't' }),
      (e) => seen.push(e.type),
      () => undefined,
      fetchImpl as unknown as typeof fetch,
    )
    client.start()
    await vi.waitFor(() => expect(seen).toEqual(['task.updated']))
    client.stop()
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://127.0.0.1:1/v1/events/stream')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer t')
  })
})

describe('detection boundaries', () => {
  it('validates the detected prompt coming from the engine', () => {
    expect(parseDetected({ prompt_id: 'abc', app: 'Teams', prompt_seconds: 20 })).toMatchObject({
      promptId: 'abc', app: 'Teams', promptSeconds: 20, reminder: 'Pense à informer les participants.',
    })
    expect(parseDetected({ prompt_id: '', prompt_seconds: 20 })).toBeNull()
    expect(parseDetected({ prompt_id: 'a', prompt_seconds: 99999 })).toBeNull()
    expect(parseDetected({ prompt_seconds: 20 })).toBeNull()
  })

  it('only accepts the three known toast answers', () => {
    expect(parseToastResponse({ promptId: 'a', action: 'record' })).toEqual({ promptId: 'a', action: 'record' })
    expect(parseToastResponse({ promptId: 'a', action: 'delete' })).toBeNull()
    expect(parseToastResponse({ promptId: 5, action: 'ignore' })).toBeNull()
    expect(parseToastResponse(null)).toBeNull()
  })

  it('meter helpers', () => {
    expect(dbToPercent(null)).toBe(0)
    expect(dbToPercent(-80)).toBe(0)
    expect(dbToPercent(0)).toBe(100)
    expect(dbToPercent(-40)).toBe(50)
    expect(micLabel(null, [])).toContain('inconnu')
    expect(micLabel(true, ['Zoom'])).toBe('oui (Zoom)')
    expect(micLabel(false, [])).toBe('non')
  })
})
