import { useEffect } from 'react'
import type { Celebration } from '../lib/progress'

export function CelebrationToast({ value, onDone }: { value: Celebration; onDone: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onDone, 3500)
    return () => window.clearTimeout(t)
  }, [value, onDone])
  return (
    <div className="celebrate" role="status">
      {value.points > 0 && <strong>+{value.points} pts</strong>}
      <span>
        {value.levelUp
          ? `Niveau ${value.levelUp} atteint !`
          : value.goalReached
            ? `Objectif du jour atteint (${value.completed}/${value.goal}) 🎉`
            : `Objectif du jour : ${Math.min(value.completed, value.goal)}/${value.goal}`}
      </span>
      {value.badges.map((b) => <span key={b} className="celebrate__badge">★ {b}</span>)}
    </div>
  )
}
