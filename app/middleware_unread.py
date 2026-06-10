"""Runs after SessionMiddleware so `request.session` is available."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class UnreadNotificationsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from app.activity_service import count_unread
        from app.database import SessionLocal

        request.state.unread_notifications = 0
        try:
            uid = request.session.get("user_id")
        except (AssertionError, AttributeError):
            uid = None
        if uid:
            db = SessionLocal()
            try:
                request.state.unread_notifications = count_unread(db, int(uid))
            finally:
                db.close()
        return await call_next(request)
