import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { useState, type KeyboardEvent } from 'react'
import type { Column, Task } from '../lib/api'
import { TaskCard } from './TaskCard'

interface Props {
  id: Column
  label: string
  hint: string
  tasks: Task[]
  onOpen: (t: Task) => void
  onCreate: (column: Column, title: string) => Promise<void>
}

export function ColumnView({ id, label, hint, tasks, onOpen, onCreate }: Props) {
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

  return (
    <section className={`column${isOver ? ' column--over' : ''}`} aria-label={label} data-column={id}>
      <header className="column__header">
        <h2>{label}</h2>
        <span className="column__count">{tasks.length}</span>
      </header>
      {hint && <p className="column__hint">{hint}</p>}
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <div ref={setNodeRef} className="column__list">
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} onOpen={onOpen} />
          ))}
        </div>
      </SortableContext>
      {id !== 'to_validate' && (
        <input
          className="quick-add"
          data-quick-add={id}
          placeholder="+ Nouvelle tâche (Entrée)"
          value={draft}
          maxLength={200}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={submit}
        />
      )}
    </section>
  )
}
