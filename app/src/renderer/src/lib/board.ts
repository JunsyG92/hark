import type { Column, Task } from './contracts.gen'

export const COLUMNS: { id: Column; label: string; hint: string }[] = [
  { id: 'to_validate', label: 'À valider', hint: 'Proposées par l’IA ou une intégration' },
  { id: 'todo', label: 'À faire', hint: '' },
  { id: 'in_progress', label: 'En cours', hint: '' },
  { id: 'done', label: 'Fait', hint: '' },
]

export const COLUMN_IDS = COLUMNS.map((c) => c.id)

export type Board = Record<Column, Task[]>

export function isColumn(value: unknown): value is Column {
  return typeof value === 'string' && (COLUMN_IDS as string[]).includes(value)
}

/** Group tasks by column, sorted by position. In "À valider", the user's own tasks come first. */
export function groupTasks(tasks: Task[]): Board {
  const board = Object.fromEntries(COLUMN_IDS.map((c) => [c, [] as Task[]])) as Board
  for (const t of tasks) board[t.column].push(t)
  for (const c of COLUMN_IDS) board[c].sort((a, b) => a.position - b.position)
  // « À valider » : the user's own tasks first (stable otherwise)
  board.to_validate.sort((a, b) => Number(b.is_mine) - Number(a.is_mine) || a.position - b.position)
  return board
}

export function findTask(board: Board, id: string): { column: Column; index: number } | null {
  for (const c of COLUMN_IDS) {
    const index = board[c].findIndex((t) => t.id === id)
    if (index >= 0) return { column: c, index }
  }
  return null
}

/** Where does a drop on `overId` (a column id or a task id) land? */
export function resolveDropTarget(board: Board, activeId: string, overId: string): { column: Column; index: number } | null {
  if (isColumn(overId)) {
    const list = board[overId].filter((t) => t.id !== activeId)
    return { column: overId, index: list.length }
  }
  const over = findTask(board, overId)
  if (!over) return null
  return { column: over.column, index: over.index }
}

/** Pure move: returns a new board with the task at `to`. */
export function moveInBoard(board: Board, taskId: string, to: { column: Column; index: number }): Board {
  const from = findTask(board, taskId)
  if (!from) return board
  const next = { ...board } as Board
  const task = { ...board[from.column][from.index]!, column: to.column }
  next[from.column] = board[from.column].filter((t) => t.id !== taskId)
  const dest = from.column === to.column ? next[from.column] : [...board[to.column]]
  const index = Math.max(0, Math.min(to.index, dest.length))
  dest.splice(index, 0, task)
  next[to.column] = dest.map((t, i) => ({ ...t, position: i }))
  if (from.column !== to.column) next[from.column] = next[from.column].map((t, i) => ({ ...t, position: i }))
  return next
}

export function sourceLabel(source: string): string {
  if (source === 'manual') return 'manuel'
  if (source.startsWith('meeting:')) return 'réunion'
  if (source.startsWith('plugin:')) return source.slice('plugin:'.length)
  return source
}
