from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hark_engine.api import create_app
from hark_engine.events import EventBus
from hark_engine.store import Database

TOKEN = "test-token-not-secret"


@pytest.fixture
def db() -> Iterator[Database]:
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def client(db: Database, bus: EventBus) -> TestClient:
    return TestClient(create_app(db, TOKEN, bus), headers={"Authorization": f"Bearer {TOKEN}"})


@pytest.fixture
def anon(db: Database) -> TestClient:
    return TestClient(create_app(db, TOKEN))
