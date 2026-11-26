import type { Person, Task } from './contracts.gen'

export function personName(p: Pick<Person, 'first_name' | 'last_name' | 'email'>): string {
  return [p.first_name, p.last_name].filter(Boolean).join(' ') || p.email
}

export function initials(p: Pick<Person, 'first_name' | 'last_name' | 'email'>): string {
  const parts = [p.first_name, p.last_name].filter(Boolean)
  const letters = parts.length ? parts.map((x) => x.trim()[0] ?? '') : [p.email[0] ?? '?']
  return letters.join('').slice(0, 2).toUpperCase()
}

/** Kanban filter: everyone, my tasks, unassigned, or one team member (person id). */
export type TaskFilter = 'all' | 'mine' | 'unassigned' | `person:${string}`

export function filterTasks(tasks: Task[], filter: TaskFilter): Task[] {
  if (filter === 'all') return tasks
  if (filter === 'mine') return tasks.filter((t) => t.is_mine)
  if (filter === 'unassigned') return tasks.filter((t) => !t.assignee_id && !t.assignee && !t.is_mine)
  const id = filter.slice('person:'.length)
  return tasks.filter((t) => t.assignee_id === id)
}

/** Open tasks per person (for the filter labels): not counting « Fait ». */
export function openCounts(tasks: Task[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const t of tasks) {
    if (t.assignee_id && t.column !== 'done') counts.set(t.assignee_id, (counts.get(t.assignee_id) ?? 0) + 1)
  }
  return counts
}

export function parseFilter(raw: string | null, people: Person[]): TaskFilter {
  if (raw === 'mine' || raw === 'unassigned' || raw === 'all') return raw
  if (raw?.startsWith('person:') && people.some((p) => `person:${p.id}` === raw)) return raw as TaskFilter
  return 'all'
}
