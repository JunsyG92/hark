import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ColumnView } from './components/ColumnView'
import { MeetingsView, type FocusRequest } from './components/MeetingsView'
import { RecordingBar } from './components/RecordingBar'
import { SettingsPanel } from './components/SettingsPanel'
import { TaskCard } from './components/TaskCard'
import { TaskEditor } from './components/TaskEditor'
import { createApi, type Column, type Person, type PersonDraft, type Task } from './lib/api'
import { filterTasks, openCounts, parseFilter, personName, type TaskFilter } from './lib/people'
import { loadCollapsed, saveCollapsed, toggle } from './lib/collapse'
import { COLUMNS, findTask, groupTasks, moveInBoard, resolveDropTarget, type Board } from './lib/board'

export function App() {
  const api = useMemo(() => createApi(window.hark.api), [])
  const [board, setBoard] = useState<Board>(() => groupTasks([]))
  const [allTasks, setAllTasks] = useState<Task[]>([])
  const [people, setPeople] = useState<Person[]>([])
  const [filter, setFilterState] = useState<TaskFilter>('all')
  const [collapsed, setCollapsed] = useState<Set<Column>>(() => loadCollapsed())
  const [entering, setEntering] = useState(true)
  const [pinned, setPinned] = useState(false)
  const peopleById = useMemo(() => new Map(people.map((p) => [p.id, p])), [people])
  const counts = useMemo(() => openCounts(allTasks), [allTasks])
  const [editing, setEditing] = useState<Task | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [view, setView] = useState<'kanban' | 'meetings'>('kanban')
  const [focusRequest, setFocusRequest] = useState<FocusRequest | null>(null)
  const [dragged, setDragged] = useState<Task | null>(null)
  const [error, setError] = useState<string | null>(null)
  const dragOrigin = useRef<Column | null>(null)

  const reload = useCallback(async () => {
    try {
      const [tasks, team] = await Promise.all([api.listTasks(), api.people().catch(() => [] as Person[])])
      setAllTasks(tasks)
      setPeople(team)
      setFilterState((f) => parseFilter(f, team))
      setBoard(groupTasks(tasks))
      setError(null)
    } catch (err) {
      setError(`Moteur injoignable : ${(err as Error).message}`)
    }
  }, [api])

  useEffect(() => {
    void reload()
    const offShown = window.hark.onShown(() => {
      setEntering(false) // replay the slide-in animation on every opening
      requestAnimationFrame(() => setEntering(true))
      void reload()
    })
    const offTasks = window.hark.onTasksChanged(() => void reload())
    return () => {
      offShown()
      offTasks()
    }
  }, [reload])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement
      if (e.key === 'Escape' && !editing && !showSettings) window.hark.hide()
      if (e.key === 'Escape') {
        setEditing(null)
        setShowSettings(false)
      }
      if (!typing && e.key === 'n') {
        e.preventDefault()
        setCollapsed((c) => {
          if (!c.has('todo')) return c
          const next = toggle(c, 'todo')
          saveCollapsed(next)
          return next
        })
        requestAnimationFrame(() => document.querySelector<HTMLInputElement>('[data-quick-add="todo"]')?.focus())
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editing, showSettings])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function onDragStart(e: DragStartEvent) {
    const pos = findTask(board, String(e.active.id))
    dragOrigin.current = pos?.column ?? null
    setDragged(pos ? board[pos.column][pos.index]! : null)
  }

  function onDragOver(e: DragOverEvent) {
    if (!e.over) return
    const activeId = String(e.active.id)
    const target = resolveDropTarget(board, activeId, String(e.over.id))
    const current = findTask(board, activeId)
    if (target && current && target.column !== current.column) setBoard((b) => moveInBoard(b, activeId, target))
  }

  async function onDragEnd(e: DragEndEvent) {
    setDragged(null)
    if (!e.over) return void reload()
    const activeId = String(e.active.id)
    const target = resolveDropTarget(board, activeId, String(e.over.id))
    if (!target) return
    const next = moveInBoard(board, activeId, target)
    setBoard(next)
    const final = findTask(next, activeId)!
    try {
      await api.moveTask(activeId, final.column, final.index)
    } catch (err) {
      setError((err as Error).message)
      await reload()
    }
  }

  async function create(column: Column, title: string) {
    // creating while filtered on a person assigns the new task to that person
    const assignee_id = filter.startsWith('person:') ? filter.slice('person:'.length) : undefined
    await api.createTask({ title, column, ...(assignee_id ? { assignee_id } : {}) })
    await reload()
  }

  function setFilter(next: TaskFilter) {
    setFilterState(next)
    try {
      localStorage.setItem('hark.filter', next)
    } catch {
      /* storage unavailable: the filter just isn't remembered */
    }
  }

  useEffect(() => {
    void Promise.resolve(window.hark.getSettings?.())
      .then((s) => s && setPinned(!s.hideOnBlur))
      .catch(() => undefined)
  }, [])

  async function togglePin() {
    const next = !pinned
    setPinned(next)
    try {
      await window.hark.setSettings({ hideOnBlur: !next })
    } catch {
      setPinned(!next)
    }
  }

  useEffect(() => {
    try {
      const saved = localStorage.getItem('hark.filter')
      if (saved) setFilterState(saved as TaskFilter)
    } catch {
      /* ignore */
    }
  }, [])

  function toggleColumn(col: Column) {
    setCollapsed((c) => {
      const next = toggle(c, col)
      saveCollapsed(next)
      return next
    })
  }

  async function createPerson(draft: PersonDraft): Promise<Person> {
    const person = await api.createPerson(draft)
    setPeople((p) => [...p, person])
    return person
  }

  const visible = useMemo(() => {
    if (filter === 'all') return board
    const keep = new Set(filterTasks(allTasks, filter).map((t) => t.id))
    return Object.fromEntries(Object.entries(board).map(([c, ts]) => [c, ts.filter((t) => keep.has(t.id))])) as Board
  }, [board, allTasks, filter])

  return (
    <div className={`panel${entering ? ' in' : ''}`}>
      <div className="surface app">
      <header className="head">
        <span className="brand" aria-hidden="true" />
        <nav className="tabs" aria-label="Vues">
          <button className={`tab${view === 'kanban' ? ' tab--on' : ''}`} onClick={() => setView('kanban')}>Kanban</button>
          <button className={`tab${view === 'meetings' ? ' tab--on' : ''}`} onClick={() => setView('meetings')}>Réunions</button>
        </nav>
        <span className="spacer" />
        <RecordingBar api={api} onError={setError} />
        <button
          className={`icon-btn${pinned ? ' icon-btn--on' : ''}`}
          title={pinned ? 'Épinglé : reste affiché quand tu cliques ailleurs' : 'Épingler (sinon le panneau se masque quand tu cliques ailleurs)'}
          aria-label="Épingler le panneau"
          aria-pressed={pinned}
          onClick={() => void togglePin()}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4h6l-1 6 3 3H7l3-3z" /><path d="M12 16v4" /></svg>
        </button>
        <button className="icon-btn" title="Réglages" aria-label="Réglages" onClick={() => setShowSettings(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
        </button>
        <button className="icon-btn" title="Masquer (Échap)" aria-label="Masquer" onClick={() => window.hark.hide()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>
      {error && <div className="banner">{error}</div>}
      {view === 'meetings' ? (
        <MeetingsView api={api} onError={setError} focusRequest={focusRequest} />
      ) : (
      <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={onDragStart} onDragOver={onDragOver} onDragEnd={(e) => void onDragEnd(e)} onDragCancel={() => void reload()}>
        <div className="filterbar">
          <svg className="filterbar__icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16l-6 8v6l-4-2v-4z" /></svg>
          <select className="filterbar__select" aria-label="Filtrer les tâches" value={filter} onChange={(e) => setFilter(e.target.value as TaskFilter)}>
            <option value="all">Toutes les tâches</option>
            <option value="mine">Mes tâches</option>
            <option value="unassigned">Non assignées</option>
            {people.length > 0 && (
              <optgroup label="Équipe">
                {people.map((p) => (
                  <option key={p.id} value={`person:${p.id}`}>
                    {personName(p)} ({counts.get(p.id) ?? 0})
                  </option>
                ))}
              </optgroup>
            )}
          </select>
          {filter !== 'all' && <button className="chip" onClick={() => setFilter('all')}>Tout afficher</button>}
          <span className="filterbar__count">{allTasks.filter((t) => t.column !== 'done').length} ouvertes</span>
        </div>
        <main className="board">
          {COLUMNS.map((c) => (
            <ColumnView key={c.id} {...c} tasks={visible[c.id]} onOpen={setEditing} onCreate={create} people={peopleById} collapsed={collapsed.has(c.id)} onToggle={toggleColumn} />
          ))}
        </main>
        <DragOverlay>{dragged && <TaskCard task={dragged} overlay person={dragged.assignee_id ? peopleById.get(dragged.assignee_id) : undefined} />}</DragOverlay>
      </DndContext>
      )}
      <footer className="foot">
        <span className="keys">
          <span><kbd>Échap</kbd> masquer</span>
          {view === 'kanban' && <span><kbd>N</kbd> nouvelle tâche</span>}
          <span><kbd>Ctrl</kbd><kbd>Alt</kbd><kbd>K</kbd> ouvrir</span>
        </span>
      </footer>
      </div>
      {editing && (
        <TaskEditor
          key={editing.id}
          task={editing}
          onClose={() => setEditing(null)}
          people={people}
          onCreatePerson={createPerson}
          onOpenEvidence={(id, ms) => {
            setFocusRequest({ id, ms, nonce: Date.now() })
            setEditing(null)
            setView('meetings')
          }}
          onSave={async (patch) => {
            await api.updateTask(editing.id, patch)
            await reload()
          }}
          onDelete={async () => {
            await api.deleteTask(editing.id)
            await reload()
          }}
          onAccept={async () => {
            await api.moveTask(editing.id, 'todo', board.todo.length)
            await reload()
          }}
        />
      )}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </div>
  )
}
