"""Team directory and task assignment (lead follow-up). Synthetic data only."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hark_engine.api import create_app
from hark_engine.events import EventBus
from hark_engine.models import PersonCreate, PersonUpdate
from hark_engine.profile import ProfileStore
from hark_engine.store import Database, DuplicateEmail, PeopleRepository, TaskRepository

TOKEN = "tok"


@pytest.fixture
def api(db: Database, tmp_path: Path):
    profile = ProfileStore(tmp_path / "profile.yaml")
    profile.save('name: "Mathieu Nesseir"\nemail: "mathieu@example.com"\n')
    app = create_app(db, TOKEN, EventBus(), profile_store=profile, data_dir=tmp_path)
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}), TestClient(app)


def test_repository_crud_unique_email_and_matching(db: Database):
    repo = PeopleRepository(db)
    paul = repo.create(
        PersonCreate(first_name="Paul", last_name="Durand", email="Paul.Durand@Example.com")
    )
    assert paul.email == "paul.durand@example.com"  # normalized
    repo.create(PersonCreate(first_name="Léa", last_name="Martin"))
    repo.create(
        PersonCreate(first_name="Léa", last_name="Bernard", email="")
    )  # empty e-mails may repeat
    with pytest.raises(DuplicateEmail):
        repo.create(PersonCreate(first_name="X", email="paul.durand@example.com"))
    assert [p.first_name for p in repo.list()] == ["Léa", "Léa", "Paul"]
    assert repo.match("paul") == paul and repo.match("PAUL DURAND") == paul
    assert repo.match("paul.durand@example.com") == paul and repo.match("durand") == paul
    assert repo.match("Léa") is None  # two Léa: ambiguous, never guess
    assert repo.match("lea martin").last_name == "Martin"  # type: ignore[union-attr]
    assert repo.match("Inconnu") is None and repo.match("") is None
    with pytest.raises(ValueError):
        PersonCreate(email="a@b.co")  # a name is required
    with pytest.raises(ValueError):
        PersonCreate(first_name="A", email="not-an-email")
    with pytest.raises(ValueError):
        repo.update(paul.id, PersonUpdate(first_name="", last_name=""))


def test_assign_rename_unassign_and_delete_person(api):
    c, _ = api
    paul = c.post(
        "/v1/people",
        json={"first_name": "Paul", "last_name": "Durand", "email": "paul@example.com"},
    ).json()
    task = c.post("/v1/tasks", json={"title": "Préparer le budget"}).json()
    assigned = c.patch(f"/v1/tasks/{task['id']}", json={"assignee_id": paul["id"]}).json()
    assert assigned["assignee_id"] == paul["id"] and assigned["assignee"] == "Paul Durand"
    assert assigned["is_mine"] is False
    assert [t["id"] for t in c.get("/v1/tasks", params={"assignee_id": paul["id"]}).json()] == [
        task["id"]
    ]
    # renaming the person keeps the task readable
    c.patch(f"/v1/people/{paul['id']}", json={"last_name": "Dupont"})
    assert c.get(f"/v1/tasks/{task['id']}").json()["assignee"] == "Paul Dupont"
    # unassign clears the link and the text
    cleared = c.patch(f"/v1/tasks/{task['id']}", json={"assignee_id": None}).json()
    assert cleared["assignee_id"] is None and cleared["assignee"] == ""
    # deleting a person keeps the name as text on their tasks
    c.patch(f"/v1/tasks/{task['id']}", json={"assignee_id": paul["id"]})
    assert c.delete(f"/v1/people/{paul['id']}").status_code == 204
    after = c.get(f"/v1/tasks/{task['id']}").json()
    assert after["assignee_id"] is None and after["assignee"] == "Paul Dupont"


def test_assigning_myself_marks_the_task_as_mine(api):
    c, _ = api
    me = c.post(
        "/v1/people",
        json={"first_name": "Mathieu", "last_name": "Nesseir", "email": "mathieu@example.com"},
    ).json()
    t = c.post("/v1/tasks", json={"title": "Revue", "assignee_id": me["id"]}).json()
    assert t["is_mine"] is True and t["assignee"] == "Mathieu Nesseir"


def test_validation_scopes_and_errors(api):
    c, anon = api
    assert anon.get("/v1/people").status_code == 401
    assert anon.post("/v1/people", json={"first_name": "A"}).status_code == 401
    assert c.post("/v1/people", json={}).status_code == 422  # no name
    assert c.post("/v1/people", json={"first_name": "A", "email": "nope"}).status_code == 422
    assert (
        c.post("/v1/people", json={"first_name": "A", "role": "x"}).status_code == 422
    )  # extra field
    c.post("/v1/people", json={"first_name": "A", "email": "a@example.com"})
    assert (
        c.post("/v1/people", json={"first_name": "B", "email": "A@example.com"}).status_code == 409
    )
    assert c.patch("/v1/people/" + "0" * 32, json={"first_name": "x"}).status_code == 404
    assert c.delete("/v1/people/" + "0" * 32).status_code == 404
    task = c.post("/v1/tasks", json={"title": "t"}).json()
    assert c.patch(f"/v1/tasks/{task['id']}", json={"assignee_id": "0" * 32}).status_code == 422
    assert c.patch(f"/v1/tasks/{task['id']}", json={"assignee_id": "../etc"}).status_code == 422
    assert c.post("/v1/tasks", json={"title": "t", "assignee_id": "0" * 32}).status_code == 422


def test_integrations_can_link_an_existing_person_by_email_but_never_create_one(api, db):
    c, _ = api
    paul = c.post(
        "/v1/people",
        json={"first_name": "Paul", "last_name": "Durand", "email": "paul@example.com"},
    ).json()
    t = c.post(
        "/v1/tasks/propose", json={"title": "Relire", "assignee_email": "PAUL@example.com"}
    ).json()
    assert (
        t["column"] == "to_validate"
        and t["assignee_id"] == paul["id"]
        and t["assignee"] == "Paul Durand"
    )
    u = c.post(
        "/v1/tasks/propose", json={"title": "X", "assignee_email": "ghost@example.com"}
    ).json()
    assert u["assignee_id"] is None and len(c.get("/v1/people").json()) == 1
    bad = c.post("/v1/tasks/propose", json={"title": "X", "assignee_email": "bad"})
    assert bad.status_code == 201 and bad.json()["assignee_id"] is None  # unknown: no link
    assert TaskRepository(db).list(assignee_id=paul["id"])[0].title == "Relire"


def test_analysis_links_the_spoken_assignee_to_the_directory(db: Database, tmp_path: Path):
    """The fake LLM assigns « Paul »: with one Paul in the team, the task is linked to him."""
    from hark_engine.models import AnalysisStatus
    from tests.test_analysis import Env  # noqa: PLC0415

    PeopleRepository(db).create(
        PersonCreate(first_name="Paul", last_name="Durand", email="paul@example.com")
    )
    e = Env(db, tmp_path)
    mid = e.meeting()
    e.service.process(mid)
    assert e.meetings.get(mid).analysis == AnalysisStatus.DONE
    paul_task = next(t for t in e.tasks.list() if t.title.startswith("Relire"))
    assert paul_task.assignee == "Paul Durand" and paul_task.assignee_id is not None
    assert paul_task.column == "to_validate" and not paul_task.is_mine


def test_people_changes_notify_the_kanban(db: Database, tmp_path: Path):
    from hark_engine.models import EventType

    bus = EventBus()
    seen: list = []
    bus.subscribe(seen.append, {EventType.TASK_UPDATED})
    app = create_app(db, TOKEN, bus, data_dir=tmp_path)
    c = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    p = c.post("/v1/people", json={"first_name": "A"}).json()
    c.patch(f"/v1/people/{p['id']}", json={"last_name": "B"})
    c.delete(f"/v1/people/{p['id']}")
    assert [e.data.get("person_id") for e in seen] == [p["id"]] * 3
