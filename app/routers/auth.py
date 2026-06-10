from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth_utils, services
from app.auth_web import session_user_id
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if session_user_id(request):
        return RedirectResponse("/orgs", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "auth_login.html", {"title": "Sign in"})


@router.post("/login")
def login_post(
    request: Request,
    mobile: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    u = services.authenticate_user(db, mobile, password)
    if not u:
        return templates.TemplateResponse(
            request,
            "auth_login.html",
            {
                "title": "Sign in",
                "error": "Invalid mobile number or password.",
                "mobile": mobile,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    request.session["user_id"] = u.id
    return RedirectResponse("/orgs", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if session_user_id(request):
        return RedirectResponse("/orgs", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request, "auth_register.html", {"title": "Create account"}
    )


@router.post("/register")
def register_post(
    request: Request,
    mobile: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        h = auth_utils.hash_password(password)
        services.create_user(db, mobile, h, full_name)
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "auth_register.html",
            {
                "title": "Create account",
                "error": str(e),
                "mobile": mobile,
                "full_name": full_name,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request,
            "auth_register.html",
            {
                "title": "Create account",
                "error": "That mobile number is already registered.",
                "mobile": mobile,
                "full_name": full_name,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
