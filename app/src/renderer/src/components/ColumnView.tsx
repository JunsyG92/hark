import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useState, type KeyboardEvent } from 'react'
import type { Column, Person, Task } from '../lib/api'
import { TaskCard } from './TaskCard'

interface Props {
  id: Column
  label: string
  hint: string
  tasks: Task[]
  onOpen: (t: Task) => void
  onCreate: (column: Column, title: string) => Promise<void>
  people?: Map<string, Person>
  collapsed?: boolean
  onToggle?: (column: Column) => void
}

/** One stacked, collapsible section of the side panel. A collapsed section still accepts drops. */
export function ColumnView({ id, label, hint, tasks, onOpen, onCreate, people, collapsed = false, onToggle }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id })
  const [draft, setDraft] = useState('')

  async function submit(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      setDraft('')
      e.currentTarget.blur()
      e.stopPropagation()
      return
    }
    if (e.key !== 'Enter' || !draft.trim()) return
    const title = draft.trim()
    setDraft('')
    await onCreate(id, title)
  }

  const mine = tasks.filter((t) => t.is_mine).length
  return (
    <section
      ref={setNodeRef}
      className={`column${isOver ? ' column--over' : ''}${collapsed ? ' column--collapsed' : ''}`}
      aria-label={label}
      data-column={id}
    >
      <button
        type="button"
        className="column__header"
        aria-expanded={!collapsed}
        aria-controls={`col-${id}`}
        onClick={() => onToggle?.(id)}
      >
        <svg className="chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" /></svg>
        <h2>{label}</h2>
        {id === 'to_validate' && mine > 0 && <span className="column__mine">{mine} pour toi</span>}
        <span className="column__count">{tasks.length}</span>
      </button>
      {!collapsed && (
        <div id={`col-${id}`} className="column__body">
          {hint && <p className="column__hint">{hint}</p>}
          <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
            <div className="column__list">
              {tasks.map((t) => (
                <TaskCard key={t.id} task={t} onOpen={onOpen} person={t.assignee_id ? people?.get(t.assignee_id) : undefined} />
              ))}
              {tasks.length === 0 && <p className="column__empty">Rien ici.</p>}
            </div>
          </SortableContext>
          {id !== 'to_validate' && (
            <input
              className="quick-add"
              data-quick-add={id}
              placeholder="+ Nouvelle tâche"
              value={draft}
              maxLength={200}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={submit}
            />
          )}
        </div>
      )}
    </section>
  )
}
