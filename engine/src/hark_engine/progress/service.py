"""Gamification ledger + summaries (day / month / year). Local data only."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date, datetime

from ..models import (
    Badge,
    Column,
    CompletedToday,
    DayStat,
    Level,
    PeriodProgress,
    ProgressSummary,
    Streak,
    Task,
    TeamMemberProgress,
    TodayProgress,
)
from ..store import Database, PeopleRepository, SettingsRepository, full_name
from . import rules


def _local_now() -> datetime:
    return datetime.now().astimezone()


class ProgressService:
    def __init__(
        self,
        db: Database,
        settings: SettingsRepository,
        now: Callable[[], datetime] = _local_now,
    ) -> None:
        self.db = db
        self._settings = settings
        self._now = now
        self._people = PeopleRepository(db)

    # ---- ledger (called on board moves) --------------------------------------------
    def on_move(self, before: Task, after: Task) -> None:
        now = self._now()
        day = now.date()
        with self.db.tx() as conn:
            if after.column is Column.DONE and before.column is not Column.DONE:
                points, on_time = rules.completion_points(after, day)
                conn.execute(
                    "INSERT OR IGNORE INTO activity (kind, task_id, title, mine, person_id, "
                    "on_time, points, at, day) VALUES ('task_completed', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (after.id, after.title, int(rules.counts_for_me(after)), after.assignee_id,
                     int(on_time), points, now.isoformat(), day.isoformat()),
                )  # fmt: skip
            elif before.column is Column.DONE and after.column is not Column.DONE:
                # un-completing gives the points back: moving in and out of « Fait » earns nothing
                conn.execute(
                    "DELETE FROM activity WHERE kind = 'task_completed' AND task_id = ?",
                    (after.id,),
                )
            if before.column is Column.TO_VALIDATE and after.column is not Column.TO_VALIDATE:
                conn.execute(
                    "INSERT OR IGNORE INTO activity (kind, task_id, title, mine, person_id, "
                    "on_time, points, at, day) "
                    "VALUES ('proposal_validated', ?, ?, 1, NULL, 0, ?, ?, ?)",
                    (
                        after.id,
                        after.title,
                        rules.POINTS_VALIDATED,
                        now.isoformat(),
                        day.isoformat(),
                    ),
                )

    # ---- summary ---------------------------------------------------------------------
    def summary(self, month: str | None = None, year: str | None = None) -> ProgressSummary:
        cfg = self._settings.get_progress()
        today = self._now().date()
        month_key = month or today.strftime("%Y-%m")
        year_key = year or today.strftime("%Y")
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT kind, task_id, title, mine, person_id, on_time, points, day FROM activity"
            ).fetchall()

        mine_done = [r for r in rows if r["kind"] == "task_completed" and r["mine"]]
        per_day: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # day -> [completed, points]
        for r in rows:
            if r["kind"] == "task_completed" and r["mine"]:
                per_day[r["day"]][0] += 1
            if r["mine"]:
                per_day[r["day"]][1] += r["points"]
        goal_days = {d for d, (c, _) in per_day.items() if c >= cfg.daily_goal}
        active = {date.fromisoformat(d) for d, (c, _) in per_day.items() if c > 0}
        current, best = rules.streaks(active, today)
        xp = sum(r["points"] for r in rows if r["mine"])
        level, start, nxt = rules.level_for(xp)

        t = today.isoformat()
        today_rows = [r for r in mine_done if r["day"] == t]
        metrics = {
            "completed": len(mine_done),
            "best_streak": best,
            "on_time": sum(1 for r in mine_done if r["on_time"]),
            "validated": sum(1 for r in rows if r["kind"] == "proposal_validated"),
            "goal_days": len(goal_days),
        }
        badges = [
            Badge(
                id=b.id,
                label=b.label,
                description=b.description,
                earned=metrics[b.metric] >= b.target,
                progress=min(metrics[b.metric], b.target),
                target=b.target,
            )
            for b in rules.BADGES
        ]
        team_counts: Counter[str] = Counter(
            r["person_id"]
            for r in rows
            if r["kind"] == "task_completed" and r["person_id"] and r["day"].startswith(month_key)
        )
        people = {p.id: p for p in self._people.list()}
        team = sorted(
            (
                TeamMemberProgress(person_id=pid, name=full_name(people[pid]), completed=n)
                for pid, n in team_counts.items()
                if pid in people
            ),
            key=lambda m: m.name.lower(),  # alphabetical: progress, not a ranking
        )
        return ProgressSummary(
            enabled=cfg.enabled,
            today=TodayProgress(
                date=t,
                completed=len(today_rows),
                goal=cfg.daily_goal,
                goal_reached=len(today_rows) >= cfg.daily_goal,
                points=per_day[t][1] if t in per_day else 0,
                tasks=[
                    CompletedToday(task_id=r["task_id"], title=r["title"], points=r["points"])
                    for r in today_rows
                ],
            ),
            streak=Streak(current=current, best=best),
            level=Level(level=level, xp=xp, level_start=start, next_at=nxt),
            month=self._period(per_day, goal_days, month_key, _previous_month(month_key)),
            year=self._period(per_day, goal_days, year_key, str(int(year_key) - 1)),
            badges=badges,
            team=team,
        )

    @staticmethod
    def _period(
        per_day: dict[str, list[int]], goal_days: set[str], key: str, previous: str
    ) -> PeriodProgress:
        days = sorted(d for d in per_day if d.startswith(key))
        return PeriodProgress(
            key=key,
            completed=sum(per_day[d][0] for d in days),
            points=sum(per_day[d][1] for d in days),
            previous_completed=sum(c for d, (c, _) in per_day.items() if d.startswith(previous)),
            days=[DayStat(date=d, completed=per_day[d][0], points=per_day[d][1]) for d in days],
            goal_days=sum(1 for d in goal_days if d.startswith(key)),
        )


def _previous_month(key: str) -> str:
    y, m = (int(x) for x in key.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
