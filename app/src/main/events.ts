/** Engine → main process event stream (SSE over loopback). */

export interface SseMessage {
  event: string
  data: string
  id?: string
}

/** Incremental SSE parser: feed it text chunks, it calls onMessage for each complete event. */
export function createSseParser(onMessage: (msg: SseMessage) => void): (chunk: string) => void {
  let buffer = ''
  let event = 'message'
  let data: string[] = []
  let id: string | undefined

  function line(raw: string): void {
    if (raw === '') {
      if (data.length) onMessage({ event, data: data.join('\n'), id })
      event = 'message'
      data = []
      id = undefined
      return
    }
    if (raw.startsWith(':')) return // comment / keep-alive
    const idx = raw.indexOf(':')
    const field = idx === -1 ? raw : raw.slice(0, idx)
    const value = idx === -1 ? '' : raw.slice(idx + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
    else if (field === 'id') id = value
  }

  return (chunk) => {
    buffer += chunk
    let nl: number
    while ((nl = buffer.search(/\r\n|\n|\r/)) !== -1) {
      const raw = buffer.slice(0, nl)
      buffer = buffer.slice(buffer[nl] === '\r' && buffer[nl + 1] === '\n' ? nl + 2 : nl + 1)
      line(raw)
    }
  }
}

export interface EngineEvent {
  id: string
  type: string
  occurred_at: string
  data: Record<string, unknown>
}

type Info = { port: number; token: string }

export class EngineEvents {
  private abort: AbortController | null = null
  private running = false

  constructor(
    private readonly getInfo: () => Promise<Info>,
    private readonly onEvent: (e: EngineEvent) => void,
    private readonly log: (msg: string) => void,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  start(): void {
    if (this.running) return
    this.running = true
    void this.loop()
  }

  stop(): void {
    this.running = false
    this.abort?.abort()
  }

  private async loop(): Promise<void> {
    let delay = 500
    while (this.running) {
      try {
        const info = await this.getInfo()
        this.abort = new AbortController()
        const res = await this.fetchImpl(`http://127.0.0.1:${info.port}/v1/events/stream`, {
          headers: { Authorization: `Bearer ${info.token}`, Accept: 'text/event-stream' },
          signal: this.abort.signal,
        })
        if (!res.ok || !res.body) throw new Error(`stream HTTP ${res.status}`)
        delay = 500
        const feed = createSseParser((m) => this.dispatch(m))
        const decoder = new TextDecoder()
        for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
          feed(decoder.decode(chunk, { stream: true }))
        }
      } catch (err) {
        if (!this.running) return
        this.log(`event stream: ${(err as Error).message}; retrying in ${delay} ms`)
      }
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(delay * 2, 10_000)
    }
  }

  private dispatch(m: SseMessage): void {
    try {
      const parsed = JSON.parse(m.data) as EngineEvent
      if (parsed && typeof parsed.type === 'string' && parsed.data && typeof parsed.data === 'object') {
        this.onEvent(parsed)
      }
    } catch {
      this.log('ignored malformed event')
    }
  }
}
