import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Priority, Task, TaskPatch } from '../lib/api'
import { sourceLabel } from '../lib/board'

interface Props {
  task: Task
  onSave: (patch: TaskPatch) => Promise<void>
  onDelete: () => Promise<void>
  onAccept: () => Promise<void>
  onClose: () => void
}

export function TaskEditor({ task, onSave, onDelete, onAccept, onClose }: Props) {
  const [title, setTitle] = useState(task.title)
  const [description, setDescription] = useState(task.description)
  const [assignee, setAssignee] = useState(task.assignee)
  const [due, setDue] = useState(task.due ?? '')
  const [priority, setPriority] = useState<Priority>(task.priority)
  const [error, setError] = useState<string | null>(null)
  const first = useRef<HTMLInputElement>(null)

  useEffect(() => first.current?.focus(), [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!title.trim()) return setError('Le titre est obligatoire')
    try {
      await onSave({ title: title.trim(), description, assignee: assignee.trim(), due: due || null, priority })
      onClose()
    } catch (err) {
      setError(String((err as Error).message))
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Modifier la tâche" onMouseDown={onClose}>
      <form className="modal__panel" onSubmit={submit} onMouseDown={(e) => e.stopPropagation()}>
        <input ref={first} className="modal__title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} aria-label="Titre" />
        <textarea value={description} rows={5} maxLength={10000} placeholder="Description" onChange={(e) => setDescription(e.target.value)} />
        <div className="modal__row">
          <label>
            Assigné
            <input value={assignee} maxLength={200} onChange={(e) => setAssignee(e.target.value)} />
          </label>
          <label>
            Échéance
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </label>
          <label>
            Priorité
            <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
              <option value="low">Basse</option>
              <option value="normal">Normale</option>
              <option value="high">Haute</option>
            </select>
          </label>
        </div>
        <p className="modal__source">
          Source : {sourceLabel(task.source)}
          {task.evidence && ` · extrait à ${formatMs(task.evidence.start_ms)}`}
          {task.confidence !== null && ` · confiance ${Math.round(task.confidence * 100)} %`}
        </p>
        {error && <p className="modal__error">{error}</p>}
        <div className="modal__actions">
          <button type="button" className="btn btn--danger" onClick={() => void onDelete().then(onClose)}>
            Supprimer
          </button>
          <span className="spacer" />
          {task.column === 'to_validate' && (
            <button type="button" className="btn" onClick={() => void onAccept().then(onClose)}>
              Valider → À faire
            </button>
          )}
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Annuler
          </button>
          <button type="submit" className="btn btn--primary">
            Enregistrer
          </button>
        </div>
      </form>
    </div>
  )
}

export function formatMs(ms: number): string {
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}
