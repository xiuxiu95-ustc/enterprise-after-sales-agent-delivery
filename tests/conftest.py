import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import create_app
from config.settings import Settings
from db.session import build_session_factory, init_db, make_engine


@pytest.fixture
def settings():
    return Settings(
        database_url="sqlite:///:memory:",
        rag_mode="local",
        auth_required=False,
        context_window_tokens=200,
        context_summary_ratio=0.6,
        recent_message_limit=10,
        autodream_min_closed_sessions=5,
        autodream_min_interval_hours=24,
    )


@pytest.fixture
def engine(settings):
    value = make_engine(settings.database_url)
    init_db(value)
    yield value
    value.dispose()


@pytest.fixture
def db(engine):
    session = build_session_factory(engine)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client(settings, engine):
    application = create_app(settings, engine)
    with TestClient(application) as value:
        yield value

