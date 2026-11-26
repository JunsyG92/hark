"""Gamification: points, anti-farming, streaks, levels, badges, day/month/year. Synthetic data."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from hark_engine.api import create_app
from hark_engine.events import EventBus
from hark_engine.models import (
    Column,
    PersonCreate,
    Priority,
    ProgressSettingsPatch,
    TaskCreate,
    TaskMove,
    TaskProposal,
)
from hark_engine.progress import ProgressService, rules
from hark_engine.store import Database, PeopleRepository, SettingsRepository, TaskRepository


class Clock:
    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self) -> datetime:
        return datetime(self.day.year, self.day.month, self.day.day, 10, 0).astimezone()


@pytest.fixture
def env(db: Database):
    clock = Clock(date(2026, 11, 26))
    tasks = TaskRepository(db)
    svc = ProgressService(db, SettingsRepository(db), now=clock)

    def complete(title: str, **kw) -> str:  # type: ignore[no-untyped-def]
        t = tasks.create(TaskCreate(title=title, **kw))
        done = tasks.move(t.id, TaskMove(column=Column.DONE, index=0))
        svc.on_move(t, done)
        return t.id

    return tasks, svc, clock, complete


# ---- pure rules -------------------------------------------------------------------------------
def test_points_rules():
    from hark_engine.models import Task

    base = dict(id="t", title="T", column=Column.DONE, position=0, source="manual",
                created_at=datetime.now(), updated_at=datetime.now())  # fmt: skip
    d = date(2026, 11, 26)
    assert rules.completion_points(Task(**base), d) == (10, False)
    assert rules.completion_points(Task(**base, due=d), d) == (15, True)  # on time
    assert rules.completion_points(Task(**base, due=d - timedelta(days=1)), d) == (
        10,
        False,
    )  # late
    assert rules.completion_points(Task(**base, priority=Priority.HIGH), d) == (15, False)
    other = Task(**base, assignee="Paul")  # someone else's task: counted for the team, no points
    assert rules.completion_points(other, d) == (0, False) and not rules.counts_for_me(other)
    assert rules.counts_for_me(Task(**base, assignee="Paul", is_mine=True))


def test_levels_and_streaks():
    assert rules.level_for(0) == (1, 0, 50)
    assert rules.level_for(49) == (1, 0, 50)
    assert rules.level_for(50) == (2, 50, 200)
    assert rules.level_for(450) == (4, 450, 800)
    d = date(2026, 11, 26)
    days = {d - timedelta(days=i) for i in (1, 2, 3)} | {d - timedelta(days=10)}
    assert rules.streaks(days, d) == (3, 3)  # nothing today yet: yesterday's streak still alive
    assert rules.streaks(days | {d}, d) == (4, 4)
    assert rules.streaks({d - timedelta(days=2)}, d) == (0, 1)  # broken
    assert rules.streaks(set(), d) == (0, 0)


# ---- ledger -------------------------------------------------------------------------------------
def test_completing_my_task_earns_points_and_today_counts(env):
    tasks, svc, clock, complete = env
    complete("Préparer la démo", priority=Priority.HIGH, due=clock.day)
    s = svc.summary()
    assert s.today.completed == 1 and s.today.points == 20  # 10 + on time + high priority
    assert s.today.tasks[0].title == "Préparer la démo" and s.level.xp == 20
    assert s.badges[0].id == "first_task" and s.badges[0].earned


def test_moving_in_and_out_of_done_cannot_farm_points(env, db):
    tasks, svc, clock, complete = env
    tid = complete("Relire le contrat")
    for _ in range(3):  # done -> todo -> done, three times
        before = tasks.get(tid)
        back = tasks.move(tid, TaskMove(column=Column.TODO, index=0))
        svc.on_move(before, back)
        assert svc.summary().today.completed == 0  # un-completing gives the points back
        done = tasks.move(tid, TaskMove(column=Column.DONE, index=0))
        svc.on_move(back, done)
    s = svc.summary()
    assert s.today.completed == 1 and s.level.xp == 10


def test_team_tasks_count_for_the_team_without_points_or_ranking(env, db):
    tasks, svc, clock, complete = env
    people = PeopleRepository(db)
    zoe = people.create(PersonCreate(first_name="Zoé", last_name="Martin"))
    ali = people.create(PersonCreate(first_name="Ali", last_name="Ben"))
    complete("Devis", assignee_id=zoe.id, assignee="Zoé Martin")
    complete("Maquette", assignee_id=zoe.id, assignee="Zoé Martin")
    complete("Relance", assignee_id=ali.id, assignee="Ali Ben")
    s = svc.summary()
    assert s.today.completed == 0 and s.level.xp == 0  # not my tasks
    assert [(m.name, m.completed) for m in s.team] == [
        ("Ali Ben", 1),
        ("Zoé Martin", 2),
    ]  # alphabetical


def test_sorting_ai_proposals_earns_a_little_once(env, db):
    tasks, svc, clock, _ = env
    t = tasks.propose(TaskProposal(title="Relancer Paul"), source="meeting:m1")
    todo = tasks.move(t.id, TaskMove(column=Column.TODO, index=0))
    svc.on_move(t, todo)
    back = tasks.move(t.id, TaskMove(column=Column.TO_VALIDATE, index=0))
    svc.on_move(todo, back)
    again = tasks.move(t.id, TaskMove(column=Column.TODO, index=0))
    svc.on_move(back, again)
    assert svc.summary().level.xp == rules.POINTS_VALIDATED


def test_daily_goal_streak_month_and_year(env, db):
    tasks, svc, clock, complete = env
    SettingsRepository(db).patch_progress(ProgressSettingsPatch(daily_goal=2))
    # 30 Oct, 24-25-26 Nov (2 tasks on the 26th)
    for day, n in (
        (date(2026, 10, 30), 1),
        (date(2026, 11, 24), 1),
        (date(2026, 11, 25), 1),
        (date(2026, 11, 26), 2),
    ):
        clock.day = day
        for i in range(n):
            complete(f"t-{day}-{i}")
    s = svc.summary()
    assert s.today.goal == 2 and s.today.goal_reached and s.today.completed == 2
    assert (s.streak.current, s.streak.best) == (3, 3)
    assert s.month.key == "2026-11" and s.month.completed == 4 and s.month.previous_completed == 1
    assert [d.date for d in s.month.days] == ["2026-11-24", "2026-11-25", "2026-11-26"]
    assert s.month.goal_days == 1
    assert s.year.key == "2026" and s.year.completed == 5 and s.year.previous_completed == 0
    october = svc.summary(month="2026-10")
    assert october.month.completed == 1 and october.month.previous_completed == 0
    assert svc.summary(year="2025").year.completed == 0


def test_badges_progress_is_capped(env):
    _, svc, _, complete = env
    for i in range(12):
        complete(f"t{i}")
    badges = {b.id: b for b in svc.summary().badges}
    assert badges["tasks_10"].earned and badges["tasks_10"].progress == 10
    assert not badges["tasks_50"].earned and badges["tasks_50"].progress == 12


# ---- API ------------------------------------------------------------------------
def test_progress_api_scopes_validation_and_board_moves(db, tmp_path):
    app = create_app(db, "tok", EventBus(), data_dir=tmp_path)
    c = TestClient(app, headers={"Authorization": "Bearer tok"})
    anon = TestClient(app)
    assert anon.get("/v1/progress").status_code == 401
    assert c.get("/v1/progress", params={"month": "2026-13"}).status_code == 422
    assert c.get("/v1/progress", params={"year": "26"}).status_code == 422
    assert c.patch("/v1/settings/progress", json={"daily_goal": 0}).status_code == 422
    assert anon.patch("/v1/settings/progress", json={"enabled": False}).status_code == 401
    assert c.patch("/v1/settings/progress", json={"daily_goal": 5}).json()["daily_goal"] == 5
    t = c.post("/v1/tasks", json={"title": "Écrire le CR"}).json()
    c.post(f"/v1/tasks/{t['id']}/move", json={"column": "done", "index": 0})
    s = c.get("/v1/progress").json()
    assert s["today"]["completed"] == 1 and s["today"]["goal"] == 5 and s["level"]["xp"] == 10
    assert s["enabled"] is True and len(s["badges"]) == len(rules.BADGES)
