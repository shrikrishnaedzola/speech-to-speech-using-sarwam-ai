"""Database setup (SQLAlchemy) supporting MySQL and SQLite."""

import os
import ssl
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# Normalize URL for MySQL if user supplies mysql:// instead of mysql+pymysql://
effective_url = DATABASE_URL
if effective_url.startswith("mysql://"):
    effective_url = effective_url.replace("mysql://", "mysql+pymysql://", 1)

def _split_ssl_mode(url: str):
    """pymysql rejects the MySQL-client `ssl-mode` URL option (Aiven's URLs use it).

    Strip it and return an equivalent SSL context: REQUIRED/PREFERRED encrypt without verifying the
    server certificate (the mysql client's meaning); VERIFY_CA / VERIFY_IDENTITY verify it.
    """
    parsed = make_url(url)
    query = dict(parsed.query)
    mode = None
    for key in ("ssl-mode", "ssl_mode"):
        mode = query.pop(key, mode)
    if mode is None:
        return url, None
    mode = str(mode).upper()
    if mode == "DISABLED":
        return parsed.set(query=query).render_as_string(hide_password=False), None
    context = ssl.create_default_context(cafile=query.get("ssl_ca"))
    if mode in ("REQUIRED", "PREFERRED"):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode == "VERIFY_CA":
        context.check_hostname = False
    query.pop("ssl_ca", None)
    return parsed.set(query=query).render_as_string(hide_password=False), context


engine_kwargs = {}
if effective_url.startswith("sqlite:///"):
    db_path = effective_url.removeprefix("sqlite:///")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False lets FastAPI threads and the pipeline task share SQLite.
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # MySQL / Cloud DB configuration
    effective_url, ssl_context = _split_ssl_mode(effective_url)
    if ssl_context is not None:
        engine_kwargs["connect_args"] = {"ssl": ssl_context}
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
