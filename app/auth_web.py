from fastapi import Request
from starlette.responses import RedirectResponse


def session_user_id(request: Request) -> int | None:
    v = request.session.get("user_id")
    return int(v) if v is not None else None


def require_session_user(request: Request) -> int | RedirectResponse:
    uid = session_user_id(request)
    if uid is None:
        return RedirectResponse("/auth/login", status_code=302)
    return uid
