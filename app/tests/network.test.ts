import { describe, expect, it, vi } from 'vitest'
import { OFFLINE_SWITCHES, blockNonLocalRequests, isAllowedUrl } from '../src/main/network'

describe('local-first lockdown', () => {
  it('only local URLs are allowed', () => {
    for (const ok of [
      'file:///app/out/renderer/index.html', 'devtools://devtools/bundled/x.html', 'data:text/html,hi', 'blob:file:///x',
      'http://127.0.0.1:47821/v1/tasks', 'http://localhost:5173/', 'ws://localhost:5173/', 'http://[::1]:8080/',
    ]) expect(isAllowedUrl(ok), ok).toBe(true)
    for (const bad of [
      'https://redirector.gvt1.com/edgedl/x', 'http://example.com/', 'https://localhost.evil.com/', 'http://127.0.0.1.evil.com/',
      'http://192.168.1.10/', 'https://localhost@evil.com/', 'ftp://127.0.0.1/', 'chrome://gpu', 'garbage', '',
    ]) expect(isAllowedUrl(bad), bad).toBe(false)
  })

  it('cancels and reports non-local requests, lets local ones through', () => {
    let listener: (d: { url: string }, cb: (r: { cancel: boolean }) => void) => void = () => undefined
    const onBlocked = vi.fn()
    blockNonLocalRequests({ webRequest: { onBeforeRequest: (_f, l) => (listener = l) } }, onBlocked)
    const cb = vi.fn()
    listener({ url: 'https://example.com/x' }, cb)
    expect(cb).toHaveBeenLastCalledWith({ cancel: true })
    expect(onBlocked).toHaveBeenCalledWith('https://example.com/x')
    listener({ url: 'http://127.0.0.1:1234/v1/tasks' }, cb)
    expect(cb).toHaveBeenLastCalledWith({ cancel: false })
    expect(onBlocked).toHaveBeenCalledTimes(1)
  })

  it('turns off Chromium background networking and makes non-local names unresolvable', () => {
    const names = OFFLINE_SWITCHES.map(([n]) => n)
    for (const n of ['disable-component-update', 'disable-background-networking', 'no-proxy-server', 'host-resolver-rules']) {
      expect(names).toContain(n)
    }
    const rules = OFFLINE_SWITCHES.find(([n]) => n === 'host-resolver-rules')![1]!
    expect(rules).toContain('MAP * ~NOTFOUND')
    expect(rules).toContain('EXCLUDE 127.0.0.1')
  })
})
