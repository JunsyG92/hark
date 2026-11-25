/**
 * Local-first lockdown of Electron's own (Chromium) networking.
 *
 * Chromium phones home by itself (e.g. `redirector.gvt1.com` for component updates). Hark never needs
 * the Internet from the desktop shell: the UI loads local files and talks to the engine on 127.0.0.1.
 * So we (1) turn off the background services and (2) make every non-local name unresolvable, then
 * (3) cancel any non-local request in the app session as a last line of defence.
 */

const LOCAL_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1'])

/** Chromium command-line switches applied before `app.whenReady()`. */
export const OFFLINE_SWITCHES: ReadonlyArray<readonly [string, string?]> = [
  ['disable-component-update'], // Widevine/CRLSet… updater (gvt1.com)
  ['disable-background-networking'],
  ['disable-domain-reliability'],
  ['disable-client-side-phishing-detection'],
  ['disable-sync'],
  ['no-pings'],
  ['no-proxy-server'], // ignore HTTP(S)_PROXY / system proxy: nothing here needs one
  // Any hostname other than localhost fails to resolve, whatever tries to connect.
  ['host-resolver-rules', 'MAP * ~NOTFOUND , EXCLUDE localhost , EXCLUDE 127.0.0.1'],
]

export function isAllowedUrl(raw: string): boolean {
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return false
  }
  switch (url.protocol) {
    case 'file:':
    case 'devtools:':
    case 'data:':
    case 'blob:':
    case 'about:':
      return true
    case 'http:':
    case 'https:':
    case 'ws:':
    case 'wss:':
      return LOCAL_HOSTS.has(url.hostname)
    default:
      return false
  }
}

interface WebRequestSession {
  webRequest: {
    onBeforeRequest: (
      filter: { urls: string[] },
      listener: (details: { url: string }, callback: (response: { cancel: boolean }) => void) => void,
    ) => void
  }
}

/** Cancel every request that is not local, and report it (it would be a bug). */
export function blockNonLocalRequests(session: WebRequestSession, onBlocked: (url: string) => void): void {
  session.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, callback) => {
    const ok = isAllowedUrl(details.url)
    if (!ok) onBlocked(details.url)
    callback({ cancel: !ok })
  })
}
