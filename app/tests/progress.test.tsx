// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CelebrationToast } from '../src/renderer/src/components/CelebrationToast'
import { ProgressView } from '../src/renderer/src/components/ProgressView'
import { createApi } from '../src/renderer/src/lib/api'
import type { ProgressSummary } from '../src/renderer/src/lib/contracts.gen'
import { celebrate, compare, intensity, levelProgress, monthCells, monthLabel, shiftMonth, yearCells } from '../src/renderer/src/lib/progress'

afterEach(cleanup)

function summary(over: Partial<ProgressSummary> = {}): ProgressSummary {
  return {
    enabled: true,
    today: { date: '2026-11-26', completed: 2, goal: 3, goal_reached: false, points: 20, tasks: [{ task_id: 'a', title: 'Préparer la démo', points: 15 }, { task_id: 'b', title: 'Relire', points: 5 }] },
    streak: { current: 4, best: 9 },
    level: { level: 2, xp: 120, level_start: 50, next_at: 200 },
    month: { key: '2026-11', completed: 12, points: 140, previous_completed: 8, days: [{ date: '2026-11-26', completed: 2, points: 20 }, { date: '2026-11-03', completed: 4, points: 40 }], goal_days: 3 },
    year: { key: '2026', completed: 80, points: 900, previous_completed: 0, days: [{ date: '2026-03-02', completed: 5, points: 50 }, { date: '2026-11-26', completed: 2, points: 20 }], goal_days: 20 },
    badges: [
      { id: 'first_task', label: 'Premier pas', description: 'x', earned: true, progress: 1, target: 1 },
      { id: 'tasks_100', label: 'Centurion', description: 'x', earned: false, progress: 80, target: 100 },
    ],
    team: [{ person_id: 'p1', name: 'Ali Ben', completed: 3 }],
    ...over,
  }
}

describe('progress helpers', () => {
  it('intensity is relative to the daily goal (4 = goal reached)', () => {
    expect([0, 1, 2, 3, 7].map((n) => intensity(n, 3))).toEqual([0, 1, 2, 4, 4])
    expect(intensity(1, 10)).toBe(1)
  })

  it('year heatmap: full Monday-first weeks, only days of that year', () => {
    const cells = yearCells(2026, [{ date: '2026-03-02', completed: 5, points: 50 }])
    expect(cells.length % 7).toBe(0)
    expect(cells.filter((c) => c.date).length).toBe(365)
    expect(cells[3]!.date).toBe('2026-01-01') // 1 Jan 2026 is a Thursday
    expect(cells.find((c) => c.date === '2026-03-02')!.completed).toBe(5)
    expect(yearCells(2024, []).filter((c) => c.date).length).toBe(366)
  })

  it('month calendar is padded to full weeks', () => {
    const cells = monthCells(2026, 11, [])
    expect(cells.length % 7).toBe(0)
    expect(cells.findIndex((c) => c.date === '2026-11-01')).toBe(6) // a Sunday
    expect(cells.filter((c) => c.date).length).toBe(30)
  })

  it('navigation and labels', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(monthLabel('2026-11')).toBe('novembre 2026')
    expect(compare(12, 8)).toBe('+50 %')
    expect(compare(4, 8)).toBe('-50 %')
    expect(compare(3, 0)).toBe('nouveau')
    expect(compare(0, 0)).toBe('—')
    expect(levelProgress({ level: 2, xp: 125, level_start: 50, next_at: 200 })).toBe(0.5)
  })

  it('celebrates points, goal reached, level up and new badges, and nothing otherwise', () => {
    const before = summary()
    const after = summary({
      today: { ...before.today, completed: 3, goal_reached: true },
      level: { level: 3, xp: 220, level_start: 200, next_at: 450 },
      badges: before.badges.map((b) => (b.id === 'tasks_100' ? { ...b, earned: true } : b)),
    })
    expect(celebrate(before, after)).toEqual({ points: 100, goalReached: true, goal: 3, completed: 3, levelUp: 3, badges: ['Centurion'] })
    expect(celebrate(before, before)).toBeNull()
    expect(celebrate(null, after)).toBeNull()
    expect(celebrate(before, { ...after, enabled: false })).toBeNull()
  })
})

describe('ProgressView', () => {
  function bridge(data: ProgressSummary) {
    const calls: string[] = []
    const api = vi.fn(async (req: { method: string; path: string }) => {
      calls.push(req.path)
      return { status: 200, body: data }
    })
    window.hark = { api, onTasksChanged: () => () => {} } as unknown as Window['hark']
    return { api, calls }
  }

  it('day: goal ring, points, streak, tasks done today, badges', async () => {
    const { api } = bridge(summary())
    await act(async () => void render(<ProgressView api={createApi(api)} />))
    expect(screen.getByRole('img', { name: '2 sur 3' })).toBeTruthy()
    expect(screen.getByText('Encore 1 pour l’objectif')).toBeTruthy()
    expect(screen.getByText('Préparer la démo')).toBeTruthy()
    expect(screen.getByText('Niv. 2')).toBeTruthy()
    expect(screen.getByText('obtenu')).toBeTruthy()
    expect(screen.getByText('80/100')).toBeTruthy()
  })

  it('month: calendar, comparison, team without ranking, navigation to the previous month', async () => {
    const { api, calls } = bridge(summary())
    await act(async () => void render(<ProgressView api={createApi(api)} />))
    await act(async () => fireEvent.click(screen.getByText('Mois')))
    expect(screen.getByText('novembre 2026')).toBeTruthy()
    expect(screen.getByText('+50 %')).toBeTruthy()
    expect(screen.getByText('Ali Ben')).toBeTruthy()
    expect(document.querySelector('[data-date="2026-11-03"]')!.className).toContain('cell--4')
    expect((screen.getByLabelText('Mois suivant') as HTMLButtonElement).disabled).toBe(true) // no future
    await act(async () => fireEvent.click(screen.getByLabelText('Mois précédent')))
    expect(calls).toContain('/v1/progress?month=2026-10')
  })

  it('year: heatmap of the whole year and best month', async () => {
    const { api } = bridge(summary())
    await act(async () => void render(<ProgressView api={createApi(api)} />))
    await act(async () => fireEvent.click(screen.getByText('Année')))
    expect(document.querySelectorAll('.heatmap .cell[data-date]').length).toBe(365)
    expect(screen.getByText('Meilleur mois : mars (5 tâches).')).toBeTruthy()
    expect(screen.getByText('nouveau')).toBeTruthy()
  })

  it('the celebration says what was earned', () => {
    render(<CelebrationToast value={{ points: 15, goalReached: true, goal: 3, completed: 3, levelUp: null, badges: ['Premier pas'] }} onDone={() => {}} />)
    expect(screen.getByText('+15 pts')).toBeTruthy()
    expect(screen.getByText(/Objectif du jour atteint/)).toBeTruthy()
    expect(screen.getByText('★ Premier pas')).toBeTruthy()
  })
})
