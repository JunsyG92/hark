"""Gamification rules (pure).

Points reward finishing YOUR work. Nothing rewards recording meetings (consent stays neutral).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from ..models import Priority, Task

POINTS_TASK = 10
BONUS_ON_TIME = 5
BONUS_HIGH_PRIORITY = 5
POINTS_VALIDATED = 2  # sorting the AI's proposals is real work too
XP_PER_LEVEL_UNIT = 50  # level n starts at 50 * (n-1)^2 XP


def counts_for_me(task: Task) -> bool:
    """My task = flagged mine, or nobody else's (no person, no free-text assignee)."""
    return task.is_mine or (task.assignee_id is None and not task.assignee.strip())


def completion_points(task: Task, day: date) -> tuple[int, bool]:
    """(points, on_time) for completing `task` on `day`. Team tasks earn no points."""
    on_time = task.due is not None and day <= task.due
    if not counts_for_me(task):
        return 0, on_time
    points = POINTS_TASK
    if on_time:
        points += BONUS_ON_TIME
    if task.priority is Priority.HIGH:
        points += BONUS_HIGH_PRIORITY
    return points, on_time


def level_for(xp: int) -> tuple[int, int, int]:
    """(level, xp at which it started, xp needed for the next one)."""
    level = int(math.isqrt(max(0, xp) // XP_PER_LEVEL_UNIT)) + 1
    return level, XP_PER_LEVEL_UNIT * (level - 1) ** 2, XP_PER_LEVEL_UNIT * level**2


def streaks(active_days: set[date], today: date) -> tuple[int, int]:
    """(current, best) runs of consecutive active days.

    A today without activity yet keeps yesterday's streak alive.
    """
    best = run = 0
    prev: date | None = None
    for d in sorted(active_days):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    start = today if today in active_days else today - timedelta(days=1)
    current = 0
    while start in active_days:
        current += 1
        start -= timedelta(days=1)
    return current, best


@dataclass(frozen=True)
class BadgeDef:
    id: str
    label: str
    description: str
    metric: str  # completed | best_streak | on_time | validated | goal_days
    target: int


BADGES: tuple[BadgeDef, ...] = (
    BadgeDef("first_task", "Premier pas", "Terminer ta première tâche", "completed", 1),
    BadgeDef("tasks_10", "Lancé", "10 tâches terminées", "completed", 10),
    BadgeDef("tasks_50", "Régulier", "50 tâches terminées", "completed", 50),
    BadgeDef("tasks_100", "Centurion", "100 tâches terminées", "completed", 100),
    BadgeDef("tasks_500", "Inarrêtable", "500 tâches terminées", "completed", 500),
    BadgeDef(
        "streak_3", "Sur la lancée", "3 jours d'affilée avec au moins une tâche", "best_streak", 3
    ),
    BadgeDef("streak_7", "Semaine parfaite", "7 jours d'affilée", "best_streak", 7),
    BadgeDef("streak_30", "Marathon", "30 jours d'affilée", "best_streak", 30),
    BadgeDef("on_time_10", "Ponctuel", "10 tâches terminées avant leur échéance", "on_time", 10),
    BadgeDef("validated_20", "Trieur", "20 propositions de l'IA traitées", "validated", 20),
    BadgeDef("goal_days_5", "Objectif tenu", "Atteindre l'objectif du jour 5 fois", "goal_days", 5),
)
