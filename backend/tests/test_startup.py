from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db, models


def _use_isolated_database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    return engine


def test_startup_creates_schema_without_seeding_when_disabled(monkeypatch):
    engine = _use_isolated_database(monkeypatch)
    monkeypatch.setattr(db.settings, "seed_on_start", False)

    db.ensure_demo_data()

    with db.SessionLocal() as session:
        assert session.query(models.Flat).count() == 0
    assert "flats" in models.Base.metadata.tables
    engine.dispose()


def test_startup_seeds_only_once_when_enabled_and_flats_are_empty(monkeypatch):
    engine = _use_isolated_database(monkeypatch)
    monkeypatch.setattr(db.settings, "seed_on_start", True)

    db.ensure_demo_data()
    db.ensure_demo_data()

    with db.SessionLocal() as session:
        assert session.query(models.Flat).count() == 43
        assert session.query(models.User).count() == 46
    engine.dispose()
