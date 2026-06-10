from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import activity_service, auth_utils, excel_export, services
from app.deps import get_current_user_api
from app.database import get_db
from app.models import Contribution, Expense, Member, OrganizationMember, User
from app.schemas import (
    ActivityRead,
    ContributionCreate,
    ContributionRead,
    ContributionUpdate,
    EventCreate,
    EventRead,
    EventUpdate,
    ExpenseCreate,
    ExpenseRead,
    ExpenseSplitRead,
    MemberBalance,
    MemberCreate,
    MemberRead,
    MemberUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgMemberInvite,
    TokenResponse,
    UserLogin,
    UserRegister,
)

router = APIRouter()


def _expense_read(e) -> ExpenseRead:
    splits = []
    for s in getattr(e, "splits", None) or []:
        member_name = s.member.name if getattr(s, "member", None) else ""
        splits.append(
            ExpenseSplitRead(
                member_id=s.member_id,
                member_name=member_name,
                amount=Decimal(str(s.amount)),
            )
        )
    return ExpenseRead(
        id=e.id,
        event_id=e.event_id,
        title=e.title,
        category=e.category,
        amount_total=Decimal(str(e.amount_total)),
        expense_date=e.expense_date,
        splits=splits,
        created_by_user_id=getattr(e, "created_by_user_id", None),
    )


def _org_member_or_404(db: Session, user: User, org_id: int):
    org = services.get_organization(db, org_id)
    if not org or not services.user_in_organization(db, user.id, org_id):
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _event_access_or_404(db: Session, user: User, event_id: int):
    if not services.user_can_access_event(db, user.id, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    ev = services.get_event(db, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def api_register(payload: UserRegister, db: Session = Depends(get_db)):
    try:
        h = auth_utils.hash_password(payload.password)
        u = services.create_user(db, payload.mobile, h, payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Mobile number already registered"
        ) from None
    return {"id": u.id, "mobile": u.mobile, "full_name": u.full_name}


@router.post("/auth/login", response_model=TokenResponse)
def api_login(payload: UserLogin, db: Session = Depends(get_db)):
    u = services.authenticate_user(db, payload.mobile, payload.password)
    if not u:
        raise HTTPException(status_code=401, detail="Invalid mobile or password")
    token = auth_utils.create_access_token(u.id)
    return TokenResponse(access_token=token)


@router.get("/me")
def api_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    s = services.user_personal_balance_summary(db, user.id)
    return {
        "id": user.id,
        "mobile": user.mobile,
        "full_name": user.full_name,
        "total_contributed": float(s["total_contributed"]),
        "total_expended": float(s["total_expended"]),
        "total_remaining": float(s["total_remaining"]),
    }


@router.get("/me/activities", response_model=list[ActivityRead])
def api_my_activities(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    rows = activity_service.list_for_user(db, user.id, limit=300)
    return [ActivityRead.model_validate(r) for r in rows]


@router.get("/me/activities/grouped")
def api_my_activities_grouped(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    rows = activity_service.list_for_user(db, user.id, limit=300)
    return activity_service.group_activities_hierarchy_json(db, rows)


@router.post("/me/activities/{activity_id}/read")
def api_mark_activity_read(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    if not activity_service.mark_read(db, user.id, activity_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/me/activities/read-all")
def api_mark_all_activities_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    n = activity_service.mark_all_read(db, user.id)
    return {"ok": True, "marked": n}


@router.get("/organizations/{org_id}/activities", response_model=list[ActivityRead])
def api_org_activities(
    org_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    rows = activity_service.list_for_org(db, user.id, org_id)
    return [ActivityRead.model_validate(r) for r in rows]


@router.get("/events/{event_id}/activities", response_model=list[ActivityRead])
def api_event_activities(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    rows = activity_service.list_for_event(db, user.id, event_id)
    return [ActivityRead.model_validate(r) for r in rows]


@router.get("/organizations", response_model=list[OrganizationRead])
def api_list_orgs(
    db: Session = Depends(get_db), user: User = Depends(get_current_user_api)
):
    return services.list_organizations_for_user(db, user.id)


@router.post("/organizations", response_model=OrganizationRead)
def api_create_org(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    return services.create_organization(db, user.id, payload.name)


@router.get("/organizations/{org_id}", response_model=OrganizationRead)
def api_get_org(
    org_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    return services.get_organization(db, org_id)


@router.post("/organizations/{org_id}/members")
def api_invite_org_member(
    org_id: int,
    payload: OrgMemberInvite,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    try:
        services.add_organization_member_by_mobile(db, org_id, payload.mobile, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return {"ok": True}


@router.patch("/organizations/{org_id}", response_model=OrganizationRead)
def api_patch_organization(
    org_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    try:
        return services.update_organization(db, org_id, user.id, payload.name)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_organization(
    org_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    try:
        services.delete_organization(db, org_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/organizations/{org_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_remove_org_membership(
    org_id: int,
    membership_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    om = db.get(OrganizationMember, membership_id)
    if not om or om.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    try:
        services.remove_organization_member(db, membership_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/events/{event_id}", response_model=EventRead)
def api_patch_event(
    event_id: int,
    payload: EventUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    try:
        return services.update_event(db, event_id, user.id, payload.name)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    try:
        services.delete_event(db, event_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/events/{event_id}/members/{member_id}", response_model=MemberRead)
def api_patch_member(
    event_id: int,
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    mem = db.get(Member, member_id)
    if not mem or mem.event_id != event_id:
        raise HTTPException(status_code=404, detail="Member not found")
    if payload.name is None and payload.mobile is None:
        raise HTTPException(status_code=400, detail="Provide name and/or mobile")
    try:
        return services.update_member(
            db,
            member_id,
            user.id,
            name=payload.name,
            mobile=payload.mobile,
        )
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.delete(
    "/events/{event_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_delete_member(
    event_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    mem = db.get(Member, member_id)
    if not mem or mem.event_id != event_id:
        raise HTTPException(status_code=404, detail="Member not found")
    try:
        services.delete_member(db, member_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/events/{event_id}/contributions/{contribution_id}",
    response_model=ContributionRead,
)
def api_patch_contribution(
    event_id: int,
    contribution_id: int,
    payload: ContributionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    c = db.get(Contribution, contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found")
    mem = db.get(Member, c.member_id)
    if not mem or mem.event_id != event_id:
        raise HTTPException(status_code=404, detail="Contribution not found")
    try:
        c2 = services.update_contribution(
            db,
            contribution_id,
            user.id,
            amount=payload.amount,
            note=payload.note,
        )
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return ContributionRead(
        id=c2.id,
        member_id=c2.member_id,
        amount=Decimal(str(c2.amount)),
        note=c2.note,
        created_at=c2.created_at.isoformat(),
        created_by_user_id=getattr(c2, "created_by_user_id", None),
    )


@router.delete(
    "/events/{event_id}/contributions/{contribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_delete_contribution(
    event_id: int,
    contribution_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    c = db.get(Contribution, contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found")
    mem = db.get(Member, c.member_id)
    if not mem or mem.event_id != event_id:
        raise HTTPException(status_code=404, detail="Contribution not found")
    try:
        services.delete_contribution(db, contribution_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/organizations/{org_id}/events", response_model=list[EventRead])
def api_list_events(
    org_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    return services.list_events_for_organization(db, org_id)


@router.post("/organizations/{org_id}/events", response_model=EventRead)
def api_create_event(
    org_id: int,
    payload: EventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _org_member_or_404(db, user, org_id)
    try:
        return services.create_event(db, org_id, user.id, payload.name)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e


@router.get("/events/{event_id}", response_model=EventRead)
def api_get_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    return ev


@router.get("/events/{event_id}/members", response_model=list[MemberRead])
def api_list_members(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    return sorted(ev.members, key=lambda m: m.id)


@router.post("/events/{event_id}/members", response_model=MemberRead)
def api_add_member(
    event_id: int,
    payload: MemberCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    try:
        return services.add_member(
            db, event_id, payload.name, user.id, payload.mobile
        )
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.post("/events/{event_id}/contributions", response_model=ContributionRead)
def api_add_contribution(
    event_id: int,
    payload: ContributionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    member = next((m for m in ev.members if m.id == payload.member_id), None)
    if not member:
        raise HTTPException(status_code=400, detail="Member not in this event")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    c = services.add_contribution(
        db, payload.member_id, payload.amount, payload.note, actor_user_id=user.id
    )
    return ContributionRead(
        id=c.id,
        member_id=c.member_id,
        amount=Decimal(str(c.amount)),
        note=c.note,
        created_at=c.created_at.isoformat(),
        created_by_user_id=getattr(c, "created_by_user_id", None),
    )


@router.get("/events/{event_id}/contributions", response_model=list[ContributionRead])
def api_list_contributions(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    rows: list[ContributionRead] = []
    for m in ev.members:
        for c in m.contributions:
            rows.append(
                ContributionRead(
                    id=c.id,
                    member_id=c.member_id,
                    amount=Decimal(str(c.amount)),
                    note=c.note,
                    created_at=c.created_at.isoformat(),
                    created_by_user_id=getattr(c, "created_by_user_id", None),
                )
            )
    rows.sort(key=lambda r: r.created_at, reverse=True)
    return rows


@router.post("/events/{event_id}/expenses", response_model=ExpenseRead)
def api_create_expense(
    event_id: int,
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    mids = {m.id for m in ev.members}
    for s in payload.splits:
        if s.member_id not in mids:
            raise HTTPException(
                status_code=400,
                detail=f"Member {s.member_id} is not in this event",
            )
    try:
        exp = services.create_expense(db, event_id, payload, actor_user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _expense_read(exp)


@router.get("/events/{event_id}/expenses", response_model=list[ExpenseRead])
def api_list_expenses(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    ordered = sorted(ev.expenses, key=lambda e: (e.expense_date, e.id), reverse=True)
    return [_expense_read(e) for e in ordered]


@router.patch("/events/{event_id}/expenses/{expense_id}", response_model=ExpenseRead)
def api_patch_expense(
    event_id: int,
    expense_id: int,
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    ev = _event_access_or_404(db, user, event_id)
    exp = db.get(Expense, expense_id)
    if not exp or exp.event_id != event_id:
        raise HTTPException(status_code=404, detail="Expense not found")
    mids = {m.id for m in ev.members}
    for s in payload.splits:
        if s.member_id not in mids:
            raise HTTPException(
                status_code=400,
                detail=f"Member {s.member_id} is not in this event",
            )
    try:
        e2 = services.update_expense(
            db, expense_id, payload, acting_user_id=user.id
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    return _expense_read(e2)


@router.delete(
    "/events/{event_id}/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def api_delete_expense(
    event_id: int,
    expense_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    exp = db.get(Expense, expense_id)
    if not exp or exp.event_id != event_id:
        raise HTTPException(status_code=404, detail="Expense not found")
    try:
        services.delete_expense(db, expense_id, user.id)
    except PermissionError as e:
        raise HTTPException(403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events/{event_id}/balances", response_model=list[MemberBalance])
def api_balances(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    return services.member_balances(db, event_id)


@router.get("/events/{event_id}/export.xlsx")
def api_export_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api),
):
    _event_access_or_404(db, user, event_id)
    out = excel_export.build_event_report_xlsx(db, event_id)
    if not out:
        raise HTTPException(status_code=404, detail="Event not found")
    content, filename = out
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
