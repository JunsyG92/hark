import type { Column } from './contracts.gen'
import { isColumn } from './board'

const KEY = 'hark.collapsed'

/** Collapsed sections, remembered per viewer (best effort: storage may be unavailable). */
export function loadCollapsed(): Set<Column> {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]') as unknown
    return new Set(Array.isArray(raw) ? raw.filter(isColumn) : [])
  } catch {
    return new Set()
  }
}

export function saveCollapsed(cols: Set<Column>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify([...cols]))
  } catch {
    /* not remembered, still works */
  }
}

export function toggle(cols: Set<Column>, col: Column): Set<Column> {
  const next = new Set(cols)
  if (next.has(col)) next.delete(col)
  else next.add(col)
  return next
}
