/** Validation of the "save a file" request coming from the kanban renderer. */

export const MAX_EXPORT_BYTES = 20 * 1024 * 1024

export function sanitizeFileName(name: string): string {
  const base = name.replace(/[^\p{L}\p{N}._ -]/gu, '_').replace(/\s+/g, ' ').trim().slice(0, 80)
  const stem = base.replace(/\.+$/, '') || 'reunion'
  return stem.toLowerCase().endsWith('.md') ? stem : `${stem}.md`
}

export function parseSaveRequest(raw: unknown): { fileName: string; content: string } | null {
  if (!raw || typeof raw !== 'object') return null
  const { suggestedName, content } = raw as Record<string, unknown>
  if (typeof suggestedName !== 'string' || typeof content !== 'string') return null
  if (Buffer.byteLength(content, 'utf8') > MAX_EXPORT_BYTES) return null
  return { fileName: sanitizeFileName(suggestedName), content }
}
