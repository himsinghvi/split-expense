from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.database import Base, engine
from app.db_migrate import run_sqlite_migrations
from app.middleware_unread import UnreadNotificationsMiddleware
from app.models import (  # noqa: F401
    Activity,
    Contribution,
    Event,
    Expense,
    ExpenseSplit,
    Member,
    Organization,
    OrganizationMember,
    User,
)
from app.routers import api as api_router
from app.routers import auth as auth_router
from app.routers import web as web_router

Base.metadata.create_all(bind=engine)
run_sqlite_migrations(engine)

app = FastAPI(
    title="Group Expense Tracker",
    description="Organizations, events, shared expenses. JSON API under /api/v1.",
    version="2.0.0",
)

# Order: last registered runs first on the request. CORS → Session → unread → routes.
app.add_middleware(UnreadNotificationsMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=1209600)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
_static_dir = BASE_DIR / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.include_router(auth_router.router)
app.include_router(web_router.router, tags=["web"])
app.include_router(api_router.router, prefix="/api/v1", tags=["api"])
