"""Database setup (SQLAlchemy) supporting MySQL and SQLite."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# Normalize URL for MySQL if user supplies mysql:// instead of mysql+pymysql://
effective_url = DATABASE_URL
if effective_url.startswith("mysql://"):
    effective_url = effective_url.replace("mysql://", "mysql+pymysql://", 1)

engine_kwargs = {}
if effective_url.startswith("sqlite:///"):
    db_path = effective_url.removeprefix("sqlite:///")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False lets FastAPI threads and the pipeline task share SQLite.
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # MySQL / Cloud DB configuration
    # pool_pre_ping prevents 'MySQL server has gone away' in serverless / connection drops
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = int(os.getenv("DB_POOL_RECYCLE", "280"))
    engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
    engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_engine(effective_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

_initialized = False


class Base(DeclarativeBase):
    pass


def init_db():
    from app import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(engine)


def ensure_db_initialized():
    """Ensure database tables exist and seed forms are loaded."""
    global _initialized
    if not _initialized:
        init_db()
        from app.services.forms_loader import load_seed_forms

        with SessionLocal() as db:
            load_seed_forms(db)
        _initialized = True


def get_db():
    """FastAPI dependency: one DB session per request."""
    ensure_db_initialized()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
