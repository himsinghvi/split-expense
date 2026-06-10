import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


def _default_database_url() -> str:
    """Local dev uses a file in the project dir. Vercel serverless FS is read-only except /tmp."""
    if os.environ.get("DATABASE_URL", "").strip():
        return os.environ["DATABASE_URL"].strip()
    if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV"):
        tmp_db = Path(tempfile.gettempdir()) / "expense_tracker_app_data.db"
        # Absolute path for SQLite (works on Linux/Vercel and Windows local tests).
        abs_path = str(tmp_db.resolve()).replace("\\", "/")
        return "sqlite:///" + abs_path
    return "sqlite:///./app_data.db"


# v2 schema (users, orgs, events). On Vercel, DB lives under /tmp unless DATABASE_URL is set (e.g. Neon).
SQLALCHEMY_DATABASE_URL = _default_database_url() or "sqlite:///./app_data.db"

_engine_kwargs: dict = {"pool_pre_ping": True}
if (SQLALCHEMY_DATABASE_URL or "").startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record) -> None:
    if engine.dialect.name == "sqlite":
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
