import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

export interface EngineInfo {
  port: number
  token: string
  version: string
}

/** Parse the engine's single-line stdout handshake. */
export function parseHandshake(line: string): EngineInfo | null {
  try {
    const msg = JSON.parse(line) as Record<string, unknown>
    if (
      msg.event === 'ready' &&
      typeof msg.port === 'number' && Number.isInteger(msg.port) && msg.port > 0 && msg.port < 65536 &&
      typeof msg.token === 'string' && msg.token.length >= 20 &&
      typeof msg.version === 'string'
    ) {
      return { port: msg.port, token: msg.token, version: msg.version }
    }
  } catch {
    /* not a handshake line */
  }
  return null
}

export interface EngineCommand {
  command: string
  args: string[]
  cwd?: string
}

/** Resolve how to launch the engine (env override > packaged binary > dev via uv). */
export function resolveEngineCommand(opts: {
  isPackaged: boolean
  resourcesPath: string
  appPath: string
  env: NodeJS.ProcessEnv
  platform: NodeJS.Platform
}): EngineCommand {
  const base = ['--sidecar']
  if (opts.env.HARK_ENGINE_CMD) {
    const [command, ...args] = opts.env.HARK_ENGINE_CMD.split(' ').filter(Boolean)
    return { command: command!, args: [...args, ...base] }
  }
  if (opts.isPackaged) {
    const exe = opts.platform === 'win32' ? 'hark-engine.exe' : 'hark-engine'
    return { command: join(opts.resourcesPath, 'engine', exe), args: base }
  }
  const engineDir = resolve(opts.appPath, '..', 'engine')
  return { command: 'uv', args: ['run', '--project', engineDir, 'hark-engine', ...base], cwd: engineDir }
}

type Listener = (info: EngineInfo) => void

/** Owns the Python sidecar: spawn, handshake, restart with backoff. */
export class Engine {
  private child: ChildProcess | null = null
  private info: EngineInfo | null = null
  private waiters: Listener[] = []
  private stopping = false
  private restarts = 0

  constructor(private readonly cmd: EngineCommand, private readonly log: (msg: string) => void) {}

  start(): void {
    this.stopping = false
    const env = { ...process.env, PYTHONUNBUFFERED: '1' }
    if (this.cmd.cwd && !existsSync(this.cmd.cwd)) this.log(`engine dir missing: ${this.cmd.cwd}`)
    const child = spawn(this.cmd.command, this.cmd.args, {
      cwd: this.cmd.cwd,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    this.child = child
    createInterface({ input: child.stdout! }).on('line', (line) => {
      const info = parseHandshake(line)
      if (info) {
        this.info = info
        this.restarts = 0
        this.log(`engine ready on 127.0.0.1:${info.port} (v${info.version})`)
        for (const w of this.waiters.splice(0)) w(info)
      }
    })
    createInterface({ input: child.stderr! }).on('line', (l) => this.log(`[engine] ${l}`))
    child.on('error', (err) => this.log(`engine spawn error: ${err.message}`))
    child.on('exit', (code, signal) => {
      this.info = null
      this.child = null
      if (this.stopping) return
      const delay = Math.min(30_000, 500 * 2 ** this.restarts++)
      this.log(`engine exited (code=${code} signal=${signal}); restarting in ${delay} ms`)
      setTimeout(() => this.start(), delay)
    })
  }

  ready(timeoutMs = 30_000): Promise<EngineInfo> {
    if (this.info) return Promise.resolve(this.info)
    return new Promise((res, rej) => {
      const t = setTimeout(() => rej(new Error('engine did not start in time')), timeoutMs)
      this.waiters.push((info) => {
        clearTimeout(t)
        res(info)
      })
    })
  }

  stop(): void {
    this.stopping = true
    if (this.child) {
      this.child.stdin?.end() // sidecar exits when stdin closes
      const c = this.child
      setTimeout(() => c.exitCode === null && c.kill(), 2000)
    }
  }
}
