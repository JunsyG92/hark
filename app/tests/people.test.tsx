// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../src/renderer/src/App'
import { TaskEditor } from '../src/renderer/src/components/TaskEditor'
import { TeamSection } from '../src/renderer/src/components/TeamSection'
import type { Person, Task } from '../src/renderer/src/lib/contracts.gen'
import { filterTasks, initials, openCounts, parseFilter, personName } from '../src/renderer/src/lib/people'

afterEach(cleanup)

const paul: Person = { id: 'p1', first_name: 'Paul', last_name: 'Durand', email: 'paul@example.com', created_at: 'x' }
const lea: Person = { id: 'p2', first_name: 'Léa', last_name: '', email: '', created_at: 'x' }

function task(over: Partial<Task>): Task {
  return {
    id: 't', title: 'T', description: '', assignee: '', due: null, priority: 'normal', column: 'todo', position: 0,
    source: 'manual', evidence: null, is_mine: false, assignee_id: null, confidence: null, created_at: 'x', updated_at: 'x', ...over,
  }
}

describe('people helpers', () => {
  it('names, initials, filters and counts', () => {
    expect(personName(paul)).toBe('Paul Durand')
    expect(personName({ first_name: '', last_name: '', email: 'x@y.z' })).toBe('x@y.z')
    expect(initials(paul)).toBe('PD')
    expect(initials(lea)).toBe('L')
    const tasks = [
      task({ id: 'a', assignee_id: 'p1', assignee: 'Paul Durand' }),
      task({ id: 'b', is_mine: true }),
      task({ id: 'c' }),
      task({ id: 'd', assignee: 'Quelqu’un' }),
      task({ id: 'e', assignee_id: 'p1', column: 'done' }),
    ]
    expect(filterTasks(tasks, 'all')).toHaveLength(5)
    expect(filterTasks(tasks, 'mine').map((t) => t.id)).toEqual(['b'])
    expect(filterTasks(tasks, 'unassigned').map((t) => t.id)).toEqual(['c'])
    expect(filterTasks(tasks, 'person:p1').map((t) => t.id)).toEqual(['a', 'e'])
    expect(openCounts(tasks).get('p1')).toBe(1) // « Fait » not counted
    expect(parseFilter('person:p1', [paul])).toBe('person:p1')
    expect(parseFilter('person:gone', [paul])).toBe('all') // deleted person → back to everything
    expect(parseFilter(null, [])).toBe('all')
  })
})

describe('assigning from the task editor', () => {
  it('assigns an existing person (the engine fills the name)', async () => {
    const onSave = vi.fn(async () => {})
    render(<TaskEditor task={task({})} people={[paul, lea]} onSave={onSave} onDelete={async () => {}} onAccept={async () => {}} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Assigné à'), { target: { value: 'p1' } })
    await act(async () => fireEvent.click(screen.getByText('Enregistrer')))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ assignee_id: 'p1' }))
    expect((onSave.mock.calls as unknown as [Record<string, unknown>][])[0]![0]).not.toHaveProperty('assignee')
  })

  it('creates a person on the fly (Prénom, Nom, e-mail) and assigns them', async () => {
    const onSave = vi.fn(async () => {})
    const created: Person = { id: 'p9', first_name: 'Inès', last_name: 'Roy', email: 'ines@example.com', created_at: 'x' }
    const onCreatePerson = vi.fn(async () => created)
    render(<TaskEditor task={task({})} people={[paul]} onSave={onSave} onDelete={async () => {}} onAccept={async () => {}} onClose={() => {}} onCreatePerson={onCreatePerson} />)
    fireEvent.change(screen.getByLabelText('Assigné à'), { target: { value: '__new' } })
    fireEvent.change(screen.getByLabelText('Prénom'), { target: { value: 'Inès' } })
    fireEvent.change(screen.getByLabelText('Nom'), { target: { value: 'Roy' } })
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: ' ines@example.com ' } })
    await act(async () => fireEvent.click(screen.getByText('Ajouter')))
    expect(onCreatePerson).toHaveBeenCalledWith({ first_name: 'Inès', last_name: 'Roy', email: 'ines@example.com' })
    await act(async () => fireEvent.click(screen.getByText('Enregistrer')))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ assignee_id: 'p9' }))
  })

  it('unassigning sends null; free text stays possible without a person', async () => {
    const onSave = vi.fn(async () => {})
    render(<TaskEditor task={task({ assignee_id: 'p1', assignee: 'Paul Durand' })} people={[paul]} onSave={onSave} onDelete={async () => {}} onAccept={async () => {}} onClose={() => {}} />)
    expect(screen.queryByLabelText('Assigné (texte libre)')).toBeNull()
    fireEvent.change(screen.getByLabelText('Assigné à'), { target: { value: '' } })
    expect(screen.getByLabelText('Assigné (texte libre)')).toBeTruthy()
    await act(async () => fireEvent.click(screen.getByText('Enregistrer')))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ assignee_id: null }))
  })
})

function bridge(people: Person[], tasks: Task[]) {
  const calls: { method: string; path: string; body?: unknown }[] = []
  const api = vi.fn(async (req: { method: string; path: string; body?: unknown }) => {
    calls.push(req)
    if (req.path === '/v1/people' && req.method === 'GET') return { status: 200, body: people }
    if (req.path === '/v1/people' && req.method === 'POST') {
      const p = { id: 'new', created_at: 'x', ...(req.body as object) } as Person
      people = [...people, p]
      return { status: 201, body: p }
    }
    if (req.path.startsWith('/v1/people/') && req.method === 'DELETE') {
      people = people.filter((p) => !req.path.endsWith(p.id))
      return { status: 204, body: null }
    }
    if (req.path.startsWith('/v1/people/') && req.method === 'PATCH') return { status: 200, body: { ...people[0], ...(req.body as object) } }
    if (req.path === '/v1/recording/status') return { status: 200, body: { recording: false, elapsed_s: 0, warnings: [] } }
    if (req.path === '/v1/tasks' && req.method === 'GET') return { status: 200, body: tasks }
    if (req.path === '/v1/tasks' && req.method === 'POST') return { status: 201, body: task({ id: 'n' }) }
    return { status: 200, body: [] }
  })
  window.hark = { api, confirm: vi.fn(async () => true), hide: vi.fn(), onShown: () => () => {}, onTasksChanged: () => () => {}, onRecordingChanged: () => () => {}, platform: 'linux' } as unknown as Window['hark']
  return calls
}

describe('Team settings', () => {
  it('adds, edits and removes team members', async () => {
    const calls = bridge([paul], [])
    await act(async () => void render(<TeamSection />))
    expect(await screen.findByText('Paul Durand')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Nouveau prénom'), { target: { value: 'Léa' } })
    fireEvent.change(screen.getByLabelText('Nouvel e-mail'), { target: { value: 'lea@example.com' } })
    await act(async () => fireEvent.click(screen.getByText('Ajouter')))
    expect(calls).toContainEqual({ method: 'POST', path: '/v1/people', body: { first_name: 'Léa', last_name: '', email: 'lea@example.com' } })
    expect(await screen.findByText('lea@example.com')).toBeTruthy()
    await act(async () => fireEvent.click(screen.getAllByText('Retirer')[0]!))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/v1/people/p1')).toBe(true))
  })
})

describe('Kanban filter (lead follow-up)', () => {
  it('shows only one person’s tasks, with their avatar, and new tasks go to them', async () => {
    const calls = bridge([paul, lea], [
      task({ id: 'a', title: 'Tâche de Paul', assignee_id: 'p1', assignee: 'Paul Durand' }),
      task({ id: 'b', title: 'Tâche de Léa', assignee_id: 'p2', assignee: 'Léa', position: 1 }),
    ])
    await act(async () => void render(<App />))
    expect(await screen.findByText('Tâche de Léa')).toBeTruthy()
    expect(screen.getByText('PD')).toBeTruthy() // avatar
    await act(async () => fireEvent.change(screen.getByLabelText('Filtrer les tâches'), { target: { value: 'person:p1' } }))
    expect(screen.queryByText('Tâche de Léa')).toBeNull()
    expect(screen.getByText('Tâche de Paul')).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Paul Durand (1)' })).toBeTruthy()
    const input = document.querySelector<HTMLInputElement>('[data-quick-add="todo"]')!
    fireEvent.change(input, { target: { value: 'Relancer le client' } })
    await act(async () => fireEvent.keyDown(input, { key: 'Enter' }))
    expect(calls).toContainEqual({ method: 'POST', path: '/v1/tasks', body: { title: 'Relancer le client', column: 'todo', assignee_id: 'p1' } })
  })
})

describe('pin button', () => {
  it('toggles « hide when clicking elsewhere » in the app settings', async () => {
    bridge([], [])
    const setSettings = vi.fn(async (p: { hideOnBlur?: boolean }) => ({ shortcut: 'Control+Alt+K', launchAtLogin: false, hideOnBlur: p.hideOnBlur ?? true }))
    Object.assign(window.hark, { getSettings: vi.fn(async () => ({ shortcut: 'Control+Alt+K', launchAtLogin: false, hideOnBlur: true })), setSettings })
    await act(async () => void render(<App />))
    const pin = screen.getByLabelText('Épingler le panneau')
    expect(pin.getAttribute('aria-pressed')).toBe('false')
    await act(async () => fireEvent.click(pin))
    expect(setSettings).toHaveBeenCalledWith({ hideOnBlur: false })
    expect(pin.getAttribute('aria-pressed')).toBe('true')
  })
})
