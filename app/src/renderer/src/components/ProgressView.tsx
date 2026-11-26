import { useCallback, useEffect, useState } from 'react'
import type { HarkApi, ProgressSummary } from '../lib/api'
import {
  compare, intensity, levelProgress, monthCells, monthLabel, MONTHS, shiftMonth, yearCells, type Cell,
} from '../lib/progress'

type Period = 'day' | 'month' | 'year'
const WEEKDAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']

function plural(n: number, word: string): string {
  return `${n} ${word}${n > 1 ? 's' : ''}`
}

function Ring({ value, goal }: { value: number; goal: number }) {
  const r = 34
  const c = 2 * Math.PI * r
  const pct = Math.min(1, value / goal)
  return (
    <svg className="ring" viewBox="0 0 84 84" role="img" aria-label={`${value} sur ${goal}`}>
      <circle className="ring__track" cx="42" cy="42" r={r} />
      <circle className="ring__fill" cx="42" cy="42" r={r} strokeDasharray={c} strokeDashoffset={c * (1 - pct)} />
      <text x="42" y="40" textAnchor="middle" className="ring__value">{value}</text>
      <text x="42" y="55" textAnchor="middle" className="ring__goal">/ {goal}</text>
    </svg>
  )
}

function Cells({ cells, goal, today, className }: { cells: Cell[]; goal: number; today: string; className: string }) {
  return (
    <div className={className}>
      {cells.map((c, i) =>
        c.date ? (
          <span
            key={c.date}
            className={`cell cell--${intensity(c.completed, goal)}${c.date === today ? ' cell--today' : ''}`}
            title={`${c.date} : ${plural(c.completed, 'tâche')}`}
            data-date={c.date}
          >
            {className === 'calendar' ? Number(c.date.slice(8)) : null}
          </span>
        ) : (
          <span key={`pad-${i}`} className="cell cell--pad" />
        ),
      )}
    </div>
  )
}

export function ProgressView({ api }: { api: HarkApi }) {
  const [period, setPeriod] = useState<Period>('day')
  const [month, setMonth] = useState<string | undefined>()
  const [year, setYear] = useState<string | undefined>()
  const [data, setData] = useState<ProgressSummary | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await api.progress({ month, year }))
    } catch {
      /* engine unreachable: the main banner says so */
    }
  }, [api, month, year])

  useEffect(() => {
    void load()
    return window.hark.onTasksChanged(() => void load())
  }, [load])

  if (!data) return <div className="progress" />
  const today = data.today.date
  const lvl = levelProgress(data.level)
  const [y, m] = data.month.key.split('-').map(Number) as [number, number]
  const currentYear = Number(today.slice(0, 4))

  return (
    <div className="progress">
      <div className="hero">
        <div className="hero__level">
          <span className="hero__badge">Niv. {data.level.level}</span>
          <div className="xp" aria-label={`${data.level.xp} XP`}>
            <div className="xp__fill" style={{ width: `${Math.round(lvl * 100)}%` }} />
          </div>
          <span className="hero__xp">{data.level.xp} / {data.level.next_at} XP</span>
        </div>
        <div className="hero__streak" title={`Record : ${plural(data.streak.best, 'jour')}`}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 .2 1.5 1 2.5 2 3 .5-3-.5-5.5.5-8z" /></svg>
          <strong>{data.streak.current}</strong> j
          <span className="hero__best">record {data.streak.best}</span>
        </div>
      </div>

      <nav className="segmented" aria-label="Période">
        {(['day', 'month', 'year'] as Period[]).map((p) => (
          <button key={p} className={period === p ? 'on' : ''} aria-pressed={period === p} onClick={() => setPeriod(p)}>
            {p === 'day' ? 'Jour' : p === 'month' ? 'Mois' : 'Année'}
          </button>
        ))}
      </nav>

      {period === 'day' && (
        <section className="period" aria-label="Aujourd’hui">
          <div className="today">
            <Ring value={data.today.completed} goal={data.today.goal} />
            <div className="today__text">
              <strong>{data.today.goal_reached ? 'Objectif du jour atteint 🎉' : `Encore ${data.today.goal - data.today.completed} pour l’objectif`}</strong>
              <span>{data.today.points} points aujourd’hui</span>
              <span className="faint">{data.streak.current > 0 ? `Série de ${plural(data.streak.current, 'jour')}` : 'Termine une tâche pour lancer ta série'}</span>
            </div>
          </div>
          <h3>Terminées aujourd’hui</h3>
          {data.today.tasks.length === 0 ? (
            <p className="faint">Rien pour l’instant. Glisse une tâche dans « Fait ».</p>
          ) : (
            <ul className="done-list">
              {data.today.tasks.map((t) => (
                <li key={t.task_id}><span>{t.title}</span><span className="faint">+{t.points}</span></li>
              ))}
            </ul>
          )}
        </section>
      )}

      {period === 'month' && (
        <section className="period" aria-label="Mois">
          <div className="period__nav">
            <button className="chip" aria-label="Mois précédent" onClick={() => setMonth(shiftMonth(data.month.key, -1))}>‹</button>
            <strong>{monthLabel(data.month.key)}</strong>
            <button className="chip" aria-label="Mois suivant" disabled={data.month.key >= today.slice(0, 7)} onClick={() => setMonth(shiftMonth(data.month.key, 1))}>›</button>
          </div>
          <div className="stats">
            <div><b>{data.month.completed}</b><span>tâches</span></div>
            <div><b>{data.month.points}</b><span>points</span></div>
            <div><b>{data.month.goal_days}</b><span>objectifs tenus</span></div>
            <div><b>{compare(data.month.completed, data.month.previous_completed)}</b><span>vs mois préc.</span></div>
          </div>
          <div className="calendar calendar--head">{WEEKDAYS.map((d, i) => <span key={i}>{d}</span>)}</div>
          <Cells cells={monthCells(y, m, data.month.days)} goal={data.today.goal} today={today} className="calendar" />
          {data.team.length > 0 && (
            <>
              <h3>Équipe ce mois-ci</h3>
              <ul className="done-list">
                {data.team.map((t) => (
                  <li key={t.person_id}><span>{t.name}</span><span className="faint">{plural(t.completed, 'tâche')}</span></li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {period === 'year' && (
        <section className="period" aria-label="Année">
          <div className="period__nav">
            <button className="chip" aria-label="Année précédente" onClick={() => setYear(String(Number(data.year.key) - 1))}>‹</button>
            <strong>{data.year.key}</strong>
            <button className="chip" aria-label="Année suivante" disabled={Number(data.year.key) >= currentYear} onClick={() => setYear(String(Number(data.year.key) + 1))}>›</button>
          </div>
          <div className="stats">
            <div><b>{data.year.completed}</b><span>tâches</span></div>
            <div><b>{data.year.points}</b><span>points</span></div>
            <div><b>{data.year.goal_days}</b><span>objectifs tenus</span></div>
            <div><b>{compare(data.year.completed, data.year.previous_completed)}</b><span>vs année préc.</span></div>
          </div>
          <Cells cells={yearCells(Number(data.year.key), data.year.days)} goal={data.today.goal} today={today} className="heatmap" />
          <BestMonth days={data.year.days} />
        </section>
      )}

      <h3 className="badges__title">Badges</h3>
      <ul className="badges">
        {data.badges.map((b) => (
          <li key={b.id} className={`badge${b.earned ? ' badge--on' : ''}`} title={b.description}>
            <span className="badge__icon" aria-hidden="true">{b.earned ? '★' : '☆'}</span>
            <span className="badge__label">{b.label}</span>
            <span className="badge__progress">{b.earned ? 'obtenu' : `${b.progress}/${b.target}`}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function BestMonth({ days }: { days: { date: string; completed: number }[] }) {
  const totals = new Map<number, number>()
  for (const d of days) totals.set(Number(d.date.slice(5, 7)), (totals.get(Number(d.date.slice(5, 7))) ?? 0) + d.completed)
  const best = [...totals.entries()].sort((a, b) => b[1] - a[1])[0]
  if (!best) return <p className="faint">Pas encore d’activité cette année.</p>
  return <p className="faint">Meilleur mois : {MONTHS[best[0] - 1]} ({plural(best[1], 'tâche')}).</p>
}

