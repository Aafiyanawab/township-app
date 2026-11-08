from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_demo_data():
    """Create the schema, and seed once only when explicitly enabled and empty."""
    from sqlalchemy import func, select

    from . import models  # noqa: F401 - register model metadata before create_all

    Base.metadata.create_all(engine)
    if not settings.seed_on_start:
        return

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(models.Flat)):
            return
        from seed.seed import seed_demo_data

        seed_demo_data(db)
