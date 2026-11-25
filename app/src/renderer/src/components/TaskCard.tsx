import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Task } from '../lib/api'
import { sourceLabel } from '../lib/board'

const PRIORITY_LABEL = { low: 'basse', normal: '', high: 'haute' } as const

export function TaskCard({ task, onOpen, overlay = false }: { task: Task; onOpen?: (t: Task) => void; overlay?: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: task.id, disabled: overlay })
  const style = { transform: CSS.Transform.toString(transform), transition }
  const overdue = task.due && task.column !== 'done' && task.due < new Date().toISOString().slice(0, 10)
  return (
    <article
      ref={setNodeRef}
      style={style}
      className={`card${isDragging ? ' card--ghost' : ''}${overlay ? ' card--overlay' : ''}${task.is_mine ? ' card--mine' : ''}`}
      data-testid="task-card"
      {...attributes}
      {...listeners}
      onClick={() => onOpen?.(task)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onOpen?.(task)
        listeners?.onKeyDown?.(e)
      }}
    >
      <div className="card__title">{task.title}</div>
      <div className="card__meta">
        {task.is_mine && <span className="pill pill--mine">moi</span>}
        {task.priority !== 'normal' && <span className={`pill pill--${task.priority}`}>{PRIORITY_LABEL[task.priority]}</span>}
        {task.assignee && <span className="card__assignee">@{task.assignee}</span>}
        {task.due && <span className={`card__due${overdue ? ' card__due--late' : ''}`}>{task.due}</span>}
        {task.source !== 'manual' && <span className="pill pill--source">{sourceLabel(task.source)}</span>}
      </div>
    </article>
  )
}
