import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.database import Base, SessionLocal, engine
from app.db_migrate import (
    ensure_expense_pool_credit_user_id,
    ensure_organization_contribution_expense_id,
    run_sqlite_migrations,
)
from app import services
from app.middleware_unread import UnreadNotificationsMiddleware
from app.models import (  # noqa: F401
    Activity,
    Event,
    Expense,
    ExpenseSplit,
    Member,
    Organization,
    OrganizationContribution,
    OrganizationMember,
    User,
)
from app.routers import api as api_router
from app.routers import auth as auth_router
from app.routers import web as web_router

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
run_sqlite_migrations(engine)
ensure_organization_contribution_expense_id(engine)
ensure_expense_pool_credit_user_id(engine)

_startup_db = SessionLocal()
try:
    n = services.backfill_expense_linked_org_contributions(_startup_db)
    if n:
        logger.info("Backfilled %s expense-linked org pool rows", n)
except Exception:
    logger.exception("Expense pool backfill failed; continuing without backfill")
    try:
        _startup_db.rollback()
    except Exception:
        pass
finally:
    _startup_db.close()

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
