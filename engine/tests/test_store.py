from __future__ import annotations

import pytest

from hark_engine.models import Column, TaskCreate, TaskMove, TaskProposal, TaskUpdate
from hark_engine.store import Database, TaskNotFound, TaskRepository


def test_migrations_apply_and_are_idempotent(tmp_path):
    path = tmp_path / "h.sqlite3"
    db = Database(path)
    v = db.schema_version
    assert v >= 1
    db.close()
    db2 = Database(path)
    assert db2.schema_version == v
    db2.close()


def test_create_and_list_order(db: Database):
    repo = TaskRepository(db)
    a = repo.create(TaskCreate(title="A"))
    b = repo.create(TaskCreate(title="B"))
    assert [t.id for t in repo.list(Column.TODO)] == [a.id, b.id]
    assert a.source == "manual"


def test_move_reorders_within_and_across_columns(db: Database):
    repo = TaskRepository(db)
    a, b, c = (repo.create(TaskCreate(title=t)) for t in "ABC")
    repo.move(c.id, TaskMove(column=Column.TODO, index=0))
    assert [t.title for t in repo.list(Column.TODO)] == ["C", "A", "B"]
    repo.move(a.id, TaskMove(column=Column.DONE, index=99))
    assert [t.title for t in repo.list(Column.TODO)] == ["C", "B"]
    assert [t.title for t in repo.list(Column.DONE)] == ["A"]
    assert b.id  # unused var guard


def test_propose_always_lands_in_to_validate(db: Database):
    repo = TaskRepository(db)
    t = repo.propose(TaskProposal(title="Envoyer le budget"), source="plugin:demo")
    assert t.column == Column.TO_VALIDATE
    assert t.source == "plugin:demo"


def test_update_partial(db: Database):
    repo = TaskRepository(db)
    t = repo.create(TaskCreate(title="X", assignee="Alice"))
    u = repo.update(t.id, TaskUpdate(title="Y"))
    assert u.title == "Y" and u.assignee == "Alice"
    assert u.updated_at >= t.updated_at


def test_missing_task(db: Database):
    repo = TaskRepository(db)
    with pytest.raises(TaskNotFound):
        repo.get("nope")
    with pytest.raises(TaskNotFound):
        repo.delete("nope")
