import { describe, expect, it, vi } from 'vitest'
import { forward, validateApiRequest } from '../src/main/apiProxy'
import { parseHandshake, resolveEngineCommand } from '../src/main/engine'
import { DEFAULT_SETTINGS, isValidAccelerator, sanitizeSettings } from '../src/main/settings'

describe('settings', () => {
  it('validates accelerators', () => {
    expect(isValidAccelerator('Control+Alt+K')).toBe(true)
    expect(isValidAccelerator('CommandOrControl+Shift+F5')).toBe(true)
    expect(isValidAccelerator('K')).toBe(false)
    expect(isValidAccelerator('Control+Control+K')).toBe(false)
    expect(isValidAccelerator('Control+Alt+')).toBe(false)
    expect(isValidAccelerator('Foo+K')).toBe(false)
  })

  it('sanitizes unknown or invalid values to defaults', () => {
    expect(sanitizeSettings({ shortcut: 'nope', launchAtLogin: 'yes', extra: 1 })).toEqual(DEFAULT_SETTINGS)
    expect(sanitizeSettings({ shortcut: 'Alt+Shift+H', launchAtLogin: true })).toEqual({ shortcut: 'Alt+Shift+H', launchAtLogin: true })
  })
})

describe('engine', () => {
  it('parses a valid handshake only', () => {
    const line = JSON.stringify({ event: 'ready', port: 47821, token: 'x'.repeat(43), version: '0.1.0' })
    expect(parseHandshake(line)).toEqual({ port: 47821, token: 'x'.repeat(43), version: '0.1.0' })
    expect(parseHandshake('INFO started')).toBeNull()
    expect(parseHandshake(JSON.stringify({ event: 'ready', port: 0, token: 'x'.repeat(43), version: '1' }))).toBeNull()
    expect(parseHandshake(JSON.stringify({ event: 'ready', port: 1, token: 'short', version: '1' }))).toBeNull()
  })

  it('resolves dev / packaged / override commands', () => {
    const base = { resourcesPath: '/res', appPath: '/repo/app', env: {}, platform: 'linux' as const }
    expect(resolveEngineCommand({ ...base, isPackaged: false })).toMatchObject({
      command: 'uv',
      args: ['run', '--project', '/repo/engine', 'hark-engine', '--sidecar'],
    })
    expect(resolveEngineCommand({ ...base, isPackaged: true, platform: 'win32' }).command).toMatch(/hark-engine\.exe$/)
    expect(resolveEngineCommand({ ...base, isPackaged: false, env: { HARK_ENGINE_CMD: 'python -m hark_engine' } })).toEqual({
      command: 'python',
      args: ['-m', 'hark_engine', '--sidecar'],
    })
  })
})

describe('api proxy', () => {
  it('only allows /v1 paths and known methods', () => {
    expect(validateApiRequest({ method: 'GET', path: '/v1/tasks' })).toEqual({ method: 'GET', path: '/v1/tasks', body: undefined })
    expect(() => validateApiRequest({ method: 'OPTIONS', path: '/v1/tasks' })).toThrow()
    expect(() => validateApiRequest({ method: 'GET', path: 'http://evil/v1' })).toThrow()
    expect(() => validateApiRequest({ method: 'GET', path: '/v1/../health' })).toThrow()
    expect(() => validateApiRequest({ method: 'GET', path: '/health' })).toThrow()
    expect(() => validateApiRequest(null)).toThrow()
  })

  it('forwards to loopback with the bearer token', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 201 }))
    const res = await forward({ method: 'POST', path: '/v1/tasks', body: { title: 'x' } }, { port: 1234, token: 'tok' }, fetchImpl as unknown as typeof fetch)
    expect(res).toEqual({ status: 201, body: { ok: 1 } })
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://127.0.0.1:1234/v1/tasks')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok')
  })
})
