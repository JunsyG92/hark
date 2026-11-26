import type { DayStat, ProgressSummary } from './contracts.gen'

const pad = (n: number): string => String(n).padStart(2, '0')
export const iso = (d: Date): string => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

/** 0..4 intensity; 4 means the daily goal was reached. */
export function intensity(completed: number, goal: number): number {
  if (completed <= 0) return 0
  if (completed >= goal) return 4
  return Math.min(3, Math.max(1, Math.ceil((3 * completed) / goal)))
}

export interface Cell {
  date: string | null // null = padding outside the period
  completed: number
}

function byDate(days: DayStat[]): Map<string, number> {
  return new Map(days.map((d) => [d.date, d.completed]))
}

/** Year heatmap: columns of weeks (Monday first), like GitHub's contribution graph. */
export function yearCells(year: number, days: DayStat[]): Cell[] {
  const counts = byDate(days)
  const first = new Date(year, 0, 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7)) // back to Monday
  const last = new Date(year, 11, 31)
  const cells: Cell[] = []
  for (const d = new Date(start); d <= last || cells.length % 7 !== 0; d.setDate(d.getDate() + 1)) {
    const key = iso(d)
    cells.push(d.getFullYear() === year ? { date: key, completed: counts.get(key) ?? 0 } : { date: null, completed: 0 })
  }
  return cells
}

/** Month calendar, Monday first, padded to full weeks. */
export function monthCells(year: number, month: number, days: DayStat[]): Cell[] {
  const counts = byDate(days)
  const first = new Date(year, month - 1, 1)
  const cells: Cell[] = Array.from({ length: (first.getDay() + 6) % 7 }, () => ({ date: null, completed: 0 }))
  for (let d = new Date(first); d.getMonth() === month - 1; d.setDate(d.getDate() + 1)) {
    const key = iso(d)
    cells.push({ date: key, completed: counts.get(key) ?? 0 })
  }
  while (cells.length % 7 !== 0) cells.push({ date: null, completed: 0 })
  return cells
}

export function shiftMonth(key: string, delta: number): string {
  const [y, m] = key.split('-').map(Number) as [number, number]
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

export function compare(current: number, previous: number): string {
  if (previous === 0) return current > 0 ? 'nouveau' : '—'
  const pct = Math.round(((current - previous) / previous) * 100)
  return `${pct > 0 ? '+' : ''}${pct} %`
}

export const MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']

export function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number) as [number, number]
  return `${MONTHS[m - 1]} ${y}`
}

export function levelProgress(level: ProgressSummary['level']): number {
  const span = level.next_at - level.level_start
  return span <= 0 ? 1 : Math.min(1, Math.max(0, (level.xp - level.level_start) / span))
}

export interface Celebration {
  points: number
  goalReached: boolean
  goal: number
  completed: number
  levelUp: number | null
  badges: string[]
}

/** What changed after an action, worth celebrating (null = nothing to show). */
export function celebrate(prev: ProgressSummary | null, next: ProgressSummary): Celebration | null {
  if (!prev || !next.enabled) return null
  const points = next.level.xp - prev.level.xp
  const earned = new Set(prev.badges.filter((b) => b.earned).map((b) => b.id))
  const badges = next.badges.filter((b) => b.earned && !earned.has(b.id)).map((b) => b.label)
  const goalReached = !prev.today.goal_reached && next.today.goal_reached
  const levelUp = next.level.level > prev.level.level ? next.level.level : null
  if (points <= 0 && !goalReached && !badges.length && !levelUp) return null
  return { points: Math.max(0, points), goalReached, goal: next.today.goal, completed: next.today.completed, levelUp, badges }
}
