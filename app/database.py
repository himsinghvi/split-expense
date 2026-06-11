import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool


def _normalize_database_url(url: str) -> str:
    """Neon and others may use postgres://; SQLAlchemy expects postgresql://. Prefer psycopg3 driver."""
    u = (url or "").strip()
    if not u:
        return u
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql://") and not u.startswith("postgresql+"):
        u = "postgresql+psycopg://" + u[len("postgresql://") :]
    return u


def _default_database_url() -> str:
    """Local dev uses ./app_data.db. Vercel requires DATABASE_URL — SQLite on serverless is not durable."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return _normalize_database_url(url)
    if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV"):
        raise RuntimeError(
            "DATABASE_URL is required on Vercel. "
            "SQLite in /tmp is wiped on cold starts and new instances, so users and orgs would disappear. "
            "Use hosted Postgres (e.g. Neon: https://neon.tech): create a database, copy the connection string, "
            "set DATABASE_URL in Vercel (Settings -> Environment Variables) for Production (and Preview if needed), "
            "then redeploy. See VERCEL.md."
        )
    return "sqlite:///./app_data.db"


SQLALCHEMY_DATABASE_URL = _default_database_url() or "sqlite:///./app_data.db"

_engine_kwargs: dict = {"pool_pre_ping": True}
_db_url = SQLALCHEMY_DATABASE_URL or ""
if _db_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif _db_url.startswith("postgresql"):
    if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV"):
        _engine_kwargs["poolclass"] = NullPool

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
