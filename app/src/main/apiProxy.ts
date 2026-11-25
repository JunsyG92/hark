/** Renderer → engine requests go through main, so the token never reaches the renderer. */

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export interface ApiRequest {
  method: HttpMethod
  path: string
  body?: unknown
}

export interface ApiResponse {
  status: number
  body: unknown
}

const METHODS = new Set<HttpMethod>(['GET', 'POST', 'PATCH', 'PUT', 'DELETE'])
const PATH_RE = /^\/v1\/[A-Za-z0-9_\-/.]*(\?[A-Za-z0-9_\-=&%.:]*)?$/

export function validateApiRequest(req: unknown): ApiRequest {
  if (!req || typeof req !== 'object') throw new Error('invalid request')
  const r = req as Record<string, unknown>
  if (typeof r.method !== 'string' || !METHODS.has(r.method as HttpMethod)) throw new Error('invalid method')
  if (typeof r.path !== 'string' || !PATH_RE.test(r.path) || r.path.includes('..')) throw new Error('invalid path')
  return { method: r.method as HttpMethod, path: r.path, body: r.body }
}

export async function forward(
  req: ApiRequest,
  engine: { port: number; token: string },
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResponse> {
  const res = await fetchImpl(`http://127.0.0.1:${engine.port}${req.path}`, {
    method: req.method,
    headers: {
      Authorization: `Bearer ${engine.token}`,
      ...(req.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: req.body !== undefined ? JSON.stringify(req.body) : undefined,
  })
  const text = await res.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }
  return { status: res.status, body }
}
