import { describe, expect, it } from 'vitest'
import type { Task } from '../src/renderer/src/lib/contracts.gen'
import { groupTasks, moveInBoard, resolveDropTarget, sourceLabel } from '../src/renderer/src/lib/board'

let n = 0
function task(column: Task['column'], position: number, extra: Partial<Task> = {}): Task {
  n += 1
  return {
    id: `t${n}`, title: `T${n}`, description: '', assignee: '', due: null, priority: 'normal',
    column, position, source: 'manual', evidence: null, is_mine: false, assignee_id: null, confidence: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', ...extra,
  }
}

describe('board', () => {
  it('groups and sorts by position', () => {
    const a = task('todo', 2), b = task('todo', 1), c = task('done', 0)
    const board = groupTasks([a, b, c])
    expect(board.todo.map((t) => t.id)).toEqual([b.id, a.id])
    expect(board.done.map((t) => t.id)).toEqual([c.id])
    expect(board.to_validate).toEqual([])
  })

  it('moves within a column', () => {
    const [a, b, c] = [task('todo', 0), task('todo', 1), task('todo', 2)]
    const board = moveInBoard(groupTasks([a!, b!, c!]), c!.id, { column: 'todo', index: 0 })
    expect(board.todo.map((t) => t.id)).toEqual([c!.id, a!.id, b!.id])
    expect(board.todo.map((t) => t.position)).toEqual([0, 1, 2])
  })

  it('moves across columns and clamps index', () => {
    const a = task('todo', 0), b = task('in_progress', 0)
    const board = moveInBoard(groupTasks([a, b]), a.id, { column: 'in_progress', index: 99 })
    expect(board.todo).toEqual([])
    expect(board.in_progress.map((t) => t.id)).toEqual([b.id, a.id])
    expect(board.in_progress[1]!.column).toBe('in_progress')
  })

  it('resolves drops on columns and on cards', () => {
    const a = task('todo', 0), b = task('done', 0), c = task('done', 1)
    const board = groupTasks([a, b, c])
    expect(resolveDropTarget(board, a.id, 'done')).toEqual({ column: 'done', index: 2 })
    expect(resolveDropTarget(board, a.id, c.id)).toEqual({ column: 'done', index: 1 })
    expect(resolveDropTarget(board, a.id, 'unknown')).toBeNull()
  })

  it('labels sources', () => {
    expect(sourceLabel('manual')).toBe('manuel')
    expect(sourceLabel('meeting:abc')).toBe('réunion')
    expect(sourceLabel('plugin:obsidian')).toBe('obsidian')
  })
})
