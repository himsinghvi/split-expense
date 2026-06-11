import re
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.activity_service import (
    emit_activity,
    event_linked_user_ids,
    org_member_user_ids,
    user_display_name,
)
from app.auth_utils import normalize_mobile, verify_password
from app.models import (
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
from app.schemas import ExpenseCreate, ExpenseSplitInput, MemberBalance


def get_user_by_mobile(db: Session, mobile: str) -> User | None:
    key = normalize_mobile(mobile)
    return db.scalar(select(User).where(User.mobile == key))


def _digits_only(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _safe_ilike_fragment(q: str) -> str:
    """Escape LIKE wildcards for use with ESCAPE '\\\\'."""
    return (
        (q or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _event_member_user_ids(db: Session, event_id: int) -> set[int]:
    rows = db.scalars(
        select(Member.user_id).where(
            Member.event_id == event_id,
            Member.user_id.isnot(None),
        )
    ).all()
    return {int(x) for x in rows if x is not None}


def _event_has_member_with_user_id(
    db: Session, event_id: int, user_id: int, *, exclude_member_id: int | None = None
) -> bool:
    q = select(Member.id).where(
        Member.event_id == event_id,
        Member.user_id == user_id,
    )
    if exclude_member_id is not None:
        q = q.where(Member.id != exclude_member_id)
    return db.scalar(q) is not None


def suggest_org_users_for_event(
    db: Session,
    event_id: int,
    acting_user_id: int,
    query: str,
    *,
    limit: int = 50,
) -> list[dict[str, int | str]]:
    """Org roster users not yet on this event; filter by display name or mobile digits."""
    if not user_can_access_event(db, acting_user_id, event_id):
        raise PermissionError("You cannot view this event.")
    ev = db.get(Event, event_id)
    if not ev:
        raise ValueError("Event not found.")
    org_id = ev.organization_id
    taken = _event_member_user_ids(db, event_id)

    stmt = (
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == org_id)
    )
    if taken:
        stmt = stmt.where(User.id.notin_(taken))

    q = (query or "").strip()
    digits = _digits_only(q)
    has_letters = bool(re.search(r"[A-Za-z\u0080-\uFFFF]", q))
    if q:
        pat = f"%{_safe_ilike_fragment(q)}%"
        if digits and not has_letters:
            stmt = stmt.where(User.mobile.contains(digits))
        elif digits:
            stmt = stmt.where(
                or_(User.full_name.ilike(pat, escape="\\"), User.mobile.contains(digits))
            )
        else:
            stmt = stmt.where(User.full_name.ilike(pat, escape="\\"))

    stmt = stmt.order_by(User.full_name.asc(), User.mobile.asc()).limit(limit)
    users = list(db.scalars(stmt).unique().all())
    return [
        {
            "user_id": u.id,
            "full_name": (u.full_name or "").strip() or u.mobile,
            "mobile": u.mobile,
        }
        for u in users
    ]


def create_user(db: Session, mobile: str, password_hash: str, full_name: str) -> User:
    u = User(
        mobile=normalize_mobile(mobile),
        password_hash=password_hash,
        full_name=full_name.strip() or normalize_mobile(mobile),
    )
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(u)
    return u


def authenticate_user(db: Session, mobile: str, plain_password: str) -> User | None:
    u = get_user_by_mobile(db, mobile)
    if not u or not verify_password(plain_password, u.password_hash):
        return None
    return u


def user_in_organization(db: Session, user_id: int, organization_id: int) -> bool:
    return (
        db.scalar(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        is not None
    )


def list_organizations_for_user(db: Session, user_id: int) -> list[Organization]:
    return list(
        db.scalars(
            select(Organization)
            .join(OrganizationMember)
            .where(OrganizationMember.user_id == user_id)
            .options(joinedload(Organization.events))
            .order_by(Organization.created_at.desc())
        ).unique().all()
    )


def get_organization(db: Session, org_id: int) -> Organization | None:
    return db.execute(
        select(Organization)
        .where(Organization.id == org_id)
        .options(
            joinedload(Organization.members).joinedload(OrganizationMember.user),
            joinedload(Organization.events),
            joinedload(Organization.org_contributions).joinedload(
                OrganizationContribution.user
            ),
        )
    ).unique().scalar_one_or_none()


def create_organization(db: Session, user_id: int, name: str) -> Organization:
    org = Organization(name=name.strip(), created_by_user_id=user_id)
    db.add(org)
    db.flush()
    # SQLite can reuse a deleted organization's id; stale member rows would violate
    # uq_org_user when we add the creator. Remove any orphan rows for this id.
    db.execute(
        delete(OrganizationMember).where(
            OrganizationMember.organization_id == org.id
        )
    )
    db.add(
        OrganizationMember(
            organization_id=org.id,
            user_id=user_id,
            created_by_user_id=user_id,
        )
    )
    emit_activity(
        db,
        recipient_user_ids=[user_id],
        organization_id=org.id,
        event_id=None,
        actor_user_id=user_id,
        kind="org_created",
        summary=f'You created organization "{org.name}"',
    )
    db.commit()
    db.refresh(org)
    return org


def add_organization_member_by_mobile(
    db: Session, organization_id: int, mobile: str, acting_user_id: int
) -> OrganizationMember:
    if not user_in_organization(db, acting_user_id, organization_id):
        raise PermissionError("You are not a member of this organization.")
    target = get_user_by_mobile(db, mobile)
    if not target:
        raise ValueError("No user registered with that mobile number.")
    exists = db.scalar(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == target.id,
        )
    )
    if exists is not None:
        raise ValueError("That user is already in this organization.")
    om = OrganizationMember(
        organization_id=organization_id,
        user_id=target.id,
        created_by_user_id=acting_user_id,
    )
    db.add(om)
    db.flush()
    org = db.get(Organization, organization_id)
    org_name = org.name if org else "an organization"
    tname = (target.full_name or target.mobile).strip()
    aname = user_display_name(db, acting_user_id)
    uids = org_member_user_ids(db, organization_id)
    emit_activity(
        db,
        recipient_user_ids=uids,
        organization_id=organization_id,
        event_id=None,
        actor_user_id=acting_user_id,
        kind="org_member_added",
        summary=f'{aname} added {tname} to "{org_name}"',
    )
    db.commit()
    db.refresh(om)
    return om


def list_events_for_organization(db: Session, organization_id: int) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .where(Event.organization_id == organization_id)
            .order_by(Event.created_at.desc())
        )
    )


def get_event(db: Session, event_id: int) -> Event | None:
    return db.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(
            joinedload(Event.organization),
            joinedload(Event.members).joinedload(Member.user),
            joinedload(Event.expenses)
            .joinedload(Expense.splits)
            .joinedload(ExpenseSplit.member),
        )
    ).unique().scalar_one_or_none()


def get_event_for_report(db: Session, event_id: int) -> Event | None:
    return db.execute(
        select(Event)
        .where(Event.id == event_id)
        .options(
            joinedload(Event.organization),
            joinedload(Event.members).joinedload(Member.user),
            joinedload(Event.expenses)
            .joinedload(Expense.splits)
            .joinedload(ExpenseSplit.member),
        )
    ).unique().scalar_one_or_none()


def user_can_access_event(db: Session, user_id: int, event_id: int) -> bool:
    ev = db.get(Event, event_id)
    if not ev:
        return False
    return user_in_organization(db, user_id, ev.organization_id)


def create_event(db: Session, organization_id: int, user_id: int, name: str) -> Event:
    if not user_in_organization(db, user_id, organization_id):
        raise PermissionError("You cannot create events in this organization.")
    u = db.get(User, user_id)
    if not u:
        raise ValueError("User not found")
    ev = Event(
        organization_id=organization_id,
        name=name.strip(),
        created_by_user_id=user_id,
    )
    db.add(ev)
    db.flush()
    db.add(
        Member(
            event_id=ev.id,
            name=u.full_name or u.mobile,
            user_id=user_id,
            created_by_user_id=user_id,
        )
    )
    db.flush()
    aname = user_display_name(db, user_id)
    uids = org_member_user_ids(db, organization_id)
    emit_activity(
        db,
        recipient_user_ids=uids,
        organization_id=organization_id,
        event_id=ev.id,
        actor_user_id=user_id,
        kind="event_created",
        summary=f'{aname} created event "{ev.name}"',
    )
    db.commit()
    db.refresh(ev)
    return ev


def add_member(
    db: Session,
    event_id: int,
    name: str,
    acting_user_id: int,
    mobile: str | None = None,
    *,
    from_org_user_id: int | None = None,
) -> Member:
    if not user_can_access_event(db, acting_user_id, event_id):
        raise PermissionError("You cannot edit this event.")

    uid: int | None = None
    name_stripped = (name or "").strip()

    if from_org_user_id is not None:
        ev = db.get(Event, event_id)
        if not ev:
            raise ValueError("Event not found.")
        if not user_in_organization(db, from_org_user_id, ev.organization_id):
            raise ValueError(
                "That person is not in this organization, so they cannot be added from the roster."
            )
        target = db.get(User, from_org_user_id)
        if not target:
            raise ValueError("That user no longer exists.")
        if _event_has_member_with_user_id(db, event_id, target.id):
            label = (target.full_name or "").strip() or target.mobile
            raise ValueError(f'"{label}" is already a member of this event.')
        uid = target.id
        name_stripped = ((target.full_name or "").strip() or target.mobile) or target.mobile
    elif mobile and (m := mobile.strip()):
        try:
            u = get_user_by_mobile(db, m)
        except ValueError as e:
            raise ValueError(str(e)) from e
        if not u:
            raise ValueError(
                "No account matches that mobile number. Ask them to register first, "
                "or pick someone from your organization list."
            )
        uid = u.id
        if not name_stripped:
            name_stripped = (u.full_name or "").strip() or u.mobile
        if _event_has_member_with_user_id(db, event_id, uid):
            raise ValueError(
                f'"{name_stripped}" is already on this event (linked to the same account).'
            )
    elif not name_stripped:
        raise ValueError(
            "Choose someone from the organization search, enter a display name, "
            "or enter a registered mobile number."
        )

    if not name_stripped:
        raise ValueError("Display name is required.")

    mem = Member(
        event_id=event_id,
        name=name_stripped,
        user_id=uid,
        created_by_user_id=acting_user_id,
    )
    db.add(mem)
    db.flush()
    ev = db.get(Event, event_id)
    if ev:
        uids = list(dict.fromkeys(event_linked_user_ids(db, event_id)))
        if mem.user_id and mem.user_id not in uids:
            uids.append(mem.user_id)
        if not uids:
            uids = [acting_user_id]
        aname = user_display_name(db, acting_user_id)
        emit_activity(
            db,
            recipient_user_ids=uids,
            organization_id=ev.organization_id,
            event_id=event_id,
            actor_user_id=acting_user_id,
            kind="member_added",
            summary=f'{aname} added "{mem.name}" to event "{ev.name}"',
        )
    db.commit()
    db.refresh(mem)
    return mem


def org_total_expenses(db: Session, organization_id: int) -> Decimal:
    v = db.scalar(
        select(func.coalesce(func.sum(Expense.amount_total), 0))
        .join(Event, Expense.event_id == Event.id)
        .where(Event.organization_id == organization_id)
    )
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def org_total_contributed(db: Session, organization_id: int) -> Decimal:
    v = db.scalar(
        select(func.coalesce(func.sum(OrganizationContribution.amount), 0)).where(
            OrganizationContribution.organization_id == organization_id
        )
    )
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def org_pool_available(db: Session, organization_id: int) -> Decimal:
    return (
        org_total_contributed(db, organization_id)
        - org_total_expenses(db, organization_id)
    ).quantize(Decimal("0.01"))


def add_org_contribution(
    db: Session,
    organization_id: int,
    user_id: int,
    amount: Decimal,
    note: str | None,
    *,
    actor_user_id: int | None = None,
) -> OrganizationContribution:
    if actor_user_id is None:
        raise ValueError("Actor required.")
    if not user_in_organization(db, actor_user_id, organization_id):
        raise PermissionError("You cannot add pool money to this organization.")
    if not user_in_organization(db, user_id, organization_id):
        raise ValueError("That person is not a member of this organization.")
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    row = OrganizationContribution(
        organization_id=organization_id,
        user_id=user_id,
        amount=amount,
        note=(note or "").strip() or None,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    org = db.get(Organization, organization_id)
    u = db.get(User, user_id)
    uname = ((u.full_name or "").strip() or u.mobile) if u else str(user_id)
    aname = user_display_name(db, actor_user_id) if actor_user_id else "Someone"
    amt = f"{amount:.2f}"
    uids = org_member_user_ids(db, organization_id)
    emit_activity(
        db,
        recipient_user_ids=uids,
        organization_id=organization_id,
        event_id=None,
        actor_user_id=actor_user_id,
        kind="contribution_added",
        summary=f'{aname} added ₹{amt} to the org pool for {uname}',
    )
    db.commit()
    db.refresh(row)
    return row


def _split_amounts(
    total: Decimal, splits: Iterable[ExpenseSplitInput]
) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    total = total.quantize(Decimal("0.01"))

    for s in splits:
        has_amt = s.amount is not None and s.amount > 0
        has_pct = s.percent is not None and s.percent > 0
        if has_amt and has_pct:
            raise ValueError("Use either amount or percent per line, not both.")
        if has_amt:
            amt = s.amount.quantize(Decimal("0.01"))  # type: ignore[union-attr]
            out[s.member_id] = out.get(s.member_id, Decimal("0")) + amt
        elif has_pct:
            amt = (total * (s.percent / Decimal("100"))).quantize(Decimal("0.01"))  # type: ignore[operator]
            out[s.member_id] = out.get(s.member_id, Decimal("0")) + amt
        else:
            raise ValueError(
                "Each split needs either a positive amount or a positive percent."
            )

    ssum = sum(out.values()).quantize(Decimal("0.01"))
    diff = (total - ssum).quantize(Decimal("0.01"))
    if abs(diff) > Decimal("0.02"):
        raise ValueError(
            f"Splits must add up to the expense total ({total}); computed sum is {ssum}."
        )
    if diff != 0 and out:
        mid = max(out.items(), key=lambda kv: kv[1])[0]
        out[mid] = (out[mid] + diff).quantize(Decimal("0.01"))

    return out


def create_expense(
    db: Session,
    event_id: int,
    data: ExpenseCreate,
    *,
    actor_user_id: int | None = None,
) -> Expense:
    if data.amount_total <= 0:
        raise ValueError("Expense total must be greater than zero.")
    if not data.splits:
        raise ValueError("Add at least one split for this expense.")

    amounts = _split_amounts(data.amount_total, data.splits)
    split_sum = sum(amounts.values()).quantize(Decimal("0.01"))
    total = data.amount_total.quantize(Decimal("0.01"))
    if split_sum != total:
        raise ValueError(
            f"Splits must equal the total ({total}); got {split_sum}. "
            "Use only amounts, or only percents for the remainder after fixed amounts."
        )

    exp = Expense(
        event_id=event_id,
        title=data.title.strip(),
        category=data.category.strip(),
        amount_total=data.amount_total,
        expense_date=data.expense_date,
        created_by_user_id=actor_user_id,
    )
    db.add(exp)
    db.flush()
    for mid, amt in amounts.items():
        db.add(ExpenseSplit(expense_id=exp.id, member_id=mid, amount=amt))
    db.flush()
    ev = db.get(Event, event_id)
    if ev:
        uids = list(dict.fromkeys(event_linked_user_ids(db, event_id)))
        if not uids and actor_user_id:
            uids = [actor_user_id]
        aname = user_display_name(db, actor_user_id) if actor_user_id else "Someone"
        # Per recipient: show their split share, not the full bill total.
        member_rows = db.execute(
            select(Member.id, Member.user_id).where(
                Member.event_id == event_id,
                Member.user_id.isnot(None),
            )
        ).all()
        user_to_member_ids: dict[int, list[int]] = {}
        for mid, uid in member_rows:
            if uid is None:
                continue
            uid = int(uid)
            user_to_member_ids.setdefault(uid, []).append(int(mid))

        def share_for_user(uid: int) -> Decimal:
            total_share = Decimal("0")
            for mid in user_to_member_ids.get(uid, []):
                total_share += amounts.get(mid, Decimal("0"))
            return total_share.quantize(Decimal("0.01"))

        summaries_by_user: dict[int, str] = {}
        for uid in uids:
            share = share_for_user(uid)
            share_fmt = format(share, ".2f")
            summaries_by_user[uid] = (
                f'{aname} added expense "{exp.title}" '
                f'(your share ₹{share_fmt}) in "{ev.name}"'
            )

        emit_activity(
            db,
            recipient_user_ids=uids,
            organization_id=ev.organization_id,
            event_id=event_id,
            actor_user_id=actor_user_id,
            kind="expense_added",
            summary=f'{aname} added expense "{exp.title}" in "{ev.name}"',
            summaries_by_user=summaries_by_user,
        )
    db.commit()
    db.refresh(exp)
    return exp


def _can_manage_expense(exp: Expense, acting_user_id: int, db: Session) -> bool:
    if exp.created_by_user_id is not None:
        return exp.created_by_user_id == acting_user_id
    ev = db.get(Event, exp.event_id)
    return ev is not None and ev.created_by_user_id == acting_user_id


def _can_manage_org_contribution(
    c: OrganizationContribution, acting_user_id: int, db: Session
) -> bool:
    if c.created_by_user_id is not None:
        return c.created_by_user_id == acting_user_id
    org = db.get(Organization, c.organization_id)
    return org is not None and org.created_by_user_id == acting_user_id


def _can_manage_member(mem: Member, acting_user_id: int, db: Session) -> bool:
    if mem.created_by_user_id is not None:
        return mem.created_by_user_id == acting_user_id
    ev = db.get(Event, mem.event_id)
    return (
        ev is not None
        and ev.created_by_user_id is not None
        and ev.created_by_user_id == acting_user_id
    )


def update_organization(
    db: Session, organization_id: int, acting_user_id: int, name: str
) -> Organization:
    org = db.get(Organization, organization_id)
    if not org:
        raise ValueError("Organization not found.")
    if org.created_by_user_id != acting_user_id:
        raise PermissionError("Only the organization creator can rename it.")
    org.name = name.strip()
    if not org.name:
        raise ValueError("Name is required.")
    db.commit()
    db.refresh(org)
    return org


def delete_organization(db: Session, organization_id: int, acting_user_id: int) -> None:
    org = db.get(Organization, organization_id)
    if not org:
        raise ValueError("Organization not found.")
    if org.created_by_user_id != acting_user_id:
        raise PermissionError("Only the organization creator can delete it.")
    eids = list(
        db.scalars(
            select(Event.id).where(Event.organization_id == organization_id)
        ).all()
    )
    if eids:
        db.execute(delete(Activity).where(Activity.event_id.in_(eids)))
    db.execute(delete(Activity).where(Activity.organization_id == organization_id))
    db.delete(org)
    db.commit()


def remove_organization_member(
    db: Session, organization_member_id: int, acting_user_id: int
) -> None:
    om = db.get(OrganizationMember, organization_member_id)
    if not om:
        raise ValueError("Membership not found.")
    if not user_in_organization(db, acting_user_id, om.organization_id):
        raise PermissionError("You are not a member of this organization.")
    org = db.get(Organization, om.organization_id)
    if not org:
        raise ValueError("Organization not found.")

    if om.user_id == acting_user_id:
        if org.created_by_user_id == acting_user_id:
            raise ValueError(
                "Organization creator cannot leave the roster; delete the organization instead."
            )
    elif om.created_by_user_id == acting_user_id:
        if om.user_id == org.created_by_user_id:
            raise ValueError("Cannot remove the organization creator from the member list.")
    else:
        raise PermissionError(
            "Only the person who invited this member can remove them (or they can leave themselves)."
        )
    db.delete(om)
    db.commit()


def update_event(db: Session, event_id: int, acting_user_id: int, name: str) -> Event:
    ev = db.get(Event, event_id)
    if not ev:
        raise ValueError("Event not found.")
    if not user_can_access_event(db, acting_user_id, event_id):
        raise PermissionError("You cannot edit this event.")
    if ev.created_by_user_id != acting_user_id:
        raise PermissionError("Only the event creator can rename it.")
    ev.name = name.strip()
    if not ev.name:
        raise ValueError("Name is required.")
    db.commit()
    db.refresh(ev)
    return ev


def delete_event(db: Session, event_id: int, acting_user_id: int) -> None:
    ev = db.get(Event, event_id)
    if not ev:
        raise ValueError("Event not found.")
    if not user_can_access_event(db, acting_user_id, event_id):
        raise PermissionError("You cannot delete this event.")
    if ev.created_by_user_id != acting_user_id:
        raise PermissionError("Only the event creator can delete it.")
    db.execute(delete(Activity).where(Activity.event_id == event_id))
    db.delete(ev)
    db.commit()


def update_member(
    db: Session,
    member_id: int,
    acting_user_id: int,
    *,
    name: str | None = None,
    mobile: str | None = None,
) -> Member:
    mem = db.get(Member, member_id)
    if not mem:
        raise ValueError("Member not found.")
    if not user_can_access_event(db, acting_user_id, mem.event_id):
        raise PermissionError("You cannot edit this event.")
    if not _can_manage_member(mem, acting_user_id, db):
        raise PermissionError("Only the person who added this member can edit them.")

    name_stripped = (name or "").strip()
    uid: int | None = mem.user_id
    if mobile is not None and (m := mobile.strip()):
        try:
            u = get_user_by_mobile(db, m)
        except ValueError as e:
            raise ValueError(str(e)) from e
        if not u:
            raise ValueError(
                "No account matches that mobile number. Ask them to register first."
            )
        if _event_has_member_with_user_id(
            db, mem.event_id, u.id, exclude_member_id=mem.id
        ):
            raise ValueError(
                "Another member on this event is already linked to that account. "
                "Remove or relink the other row first."
            )
        uid = u.id
        if not name_stripped:
            name_stripped = (u.full_name or "").strip() or u.mobile
    if name_stripped:
        mem.name = name_stripped
    mem.user_id = uid
    db.commit()
    db.refresh(mem)
    return mem


def delete_member(db: Session, member_id: int, acting_user_id: int) -> None:
    mem = db.get(Member, member_id)
    if not mem:
        raise ValueError("Member not found.")
    if not user_can_access_event(db, acting_user_id, mem.event_id):
        raise PermissionError("You cannot edit this event.")
    if not _can_manage_member(mem, acting_user_id, db):
        raise PermissionError("Only the person who added this member can remove them.")
    n_splits = int(
        db.scalar(
            select(func.count())
            .select_from(ExpenseSplit)
            .where(ExpenseSplit.member_id == member_id)
        )
        or 0
    )
    if n_splits:
        raise ValueError(
            "This member has expense splits in this event. "
            "Remove or reassign those before deleting the member."
        )
    db.delete(mem)
    db.commit()


def update_org_contribution(
    db: Session,
    contribution_id: int,
    acting_user_id: int,
    *,
    amount: Decimal,
    note: str | None,
) -> OrganizationContribution:
    c = db.get(OrganizationContribution, contribution_id)
    if not c:
        raise ValueError("Pool entry not found.")
    if not user_in_organization(db, acting_user_id, c.organization_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_org_contribution(c, acting_user_id, db):
        raise PermissionError("Only the person who logged this pool entry can edit it.")
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    c.amount = amount
    c.note = (note or "").strip() or None
    db.commit()
    db.refresh(c)
    return c


def delete_org_contribution(db: Session, contribution_id: int, acting_user_id: int) -> None:
    c = db.get(OrganizationContribution, contribution_id)
    if not c:
        raise ValueError("Pool entry not found.")
    if not user_in_organization(db, acting_user_id, c.organization_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_org_contribution(c, acting_user_id, db):
        raise PermissionError("Only the person who logged this pool entry can delete it.")
    db.delete(c)
    db.commit()


def update_expense(
    db: Session,
    expense_id: int,
    data: ExpenseCreate,
    *,
    acting_user_id: int,
) -> Expense:
    exp = db.get(Expense, expense_id)
    if not exp:
        raise ValueError("Expense not found.")
    if not user_can_access_event(db, acting_user_id, exp.event_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_expense(exp, acting_user_id, db):
        raise PermissionError("Only the person who created this expense can edit it.")

    amounts = _split_amounts(data.amount_total, data.splits)
    split_sum = sum(amounts.values()).quantize(Decimal("0.01"))
    total = data.amount_total.quantize(Decimal("0.01"))
    if split_sum != total:
        raise ValueError(
            f"Splits must equal the total ({total}); got {split_sum}. "
            "Use only amounts, or only percents for the remainder after fixed amounts."
        )

    exp.title = data.title.strip()
    exp.category = data.category.strip()
    exp.amount_total = data.amount_total
    exp.expense_date = data.expense_date
    db.execute(delete(ExpenseSplit).where(ExpenseSplit.expense_id == expense_id))
    for mid, amt in amounts.items():
        db.add(ExpenseSplit(expense_id=exp.id, member_id=mid, amount=amt))
    db.commit()
    db.refresh(exp)
    return exp


def delete_expense(db: Session, expense_id: int, acting_user_id: int) -> None:
    exp = db.get(Expense, expense_id)
    if not exp:
        raise ValueError("Expense not found.")
    if not user_can_access_event(db, acting_user_id, exp.event_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_expense(exp, acting_user_id, db):
        raise PermissionError("Only the person who created this expense can delete it.")
    db.delete(exp)
    db.commit()


def user_can_manage_expense(
    db: Session, expense_id: int, acting_user_id: int
) -> bool:
    exp = db.get(Expense, expense_id)
    if not exp or not user_can_access_event(db, acting_user_id, exp.event_id):
        return False
    return _can_manage_expense(exp, acting_user_id, db)


def user_can_manage_org_contribution(
    db: Session, contribution_id: int, acting_user_id: int
) -> bool:
    c = db.get(OrganizationContribution, contribution_id)
    if not c or not user_in_organization(db, acting_user_id, c.organization_id):
        return False
    return _can_manage_org_contribution(c, acting_user_id, db)


def user_can_manage_member(
    db: Session, member_id: int, acting_user_id: int
) -> bool:
    mem = db.get(Member, member_id)
    if not mem or not user_can_access_event(db, acting_user_id, mem.event_id):
        return False
    return _can_manage_member(mem, acting_user_id, db)


def user_can_remove_org_membership(
    db: Session, organization_member_id: int, acting_user_id: int
) -> bool:
    om = db.get(OrganizationMember, organization_member_id)
    if not om or not user_in_organization(db, acting_user_id, om.organization_id):
        return False
    org = db.get(Organization, om.organization_id)
    if not org:
        return False
    if om.user_id == acting_user_id:
        if org.created_by_user_id == acting_user_id:
            return False
        return True
    if om.created_by_user_id == acting_user_id:
        return om.user_id != org.created_by_user_id
    return False


def user_personal_balance_summary(db: Session, user_id: int) -> dict[str, Decimal]:
    """Org-wide pool entries for this user vs expense splits on any event member row."""
    z = Decimal("0").quantize(Decimal("0.01"))
    contrib_sum = db.scalar(
        select(func.coalesce(func.sum(OrganizationContribution.amount), 0)).where(
            OrganizationContribution.user_id == user_id
        )
    )
    member_ids = list(
        db.scalars(select(Member.id).where(Member.user_id == user_id)).all()
    )
    split_sum = z
    if member_ids:
        v = db.scalar(
            select(func.coalesce(func.sum(ExpenseSplit.amount), 0)).where(
                ExpenseSplit.member_id.in_(member_ids)
            )
        )
        split_sum = Decimal(str(v or 0)).quantize(Decimal("0.01"))
    contributed = Decimal(str(contrib_sum or 0)).quantize(Decimal("0.01"))
    remaining = (contributed - split_sum).quantize(Decimal("0.01"))
    return {
        "total_contributed": contributed,
        "total_expended": split_sum,
        "total_remaining": remaining,
    }


def org_member_balances(db: Session, organization_id: int) -> list[MemberBalance]:
    """Per org roster user: pooled (org contributions) vs expended (all events in org)."""
    oms = list(
        db.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .options(joinedload(OrganizationMember.user))
            .order_by(OrganizationMember.id)
        ).unique().all()
    )
    if not oms:
        return []
    uids = [om.user_id for om in oms]

    contrib_by = {uid: Decimal("0") for uid in uids}
    for uid, amt in db.execute(
        select(OrganizationContribution.user_id, OrganizationContribution.amount).where(
            OrganizationContribution.organization_id == organization_id,
            OrganizationContribution.user_id.in_(uids),
        )
    ).all():
        contrib_by[int(uid)] += Decimal(str(amt))

    exp_rows = db.execute(
        select(Member.user_id, func.sum(ExpenseSplit.amount))
        .join(ExpenseSplit, ExpenseSplit.member_id == Member.id)
        .join(Expense, Expense.id == ExpenseSplit.expense_id)
        .join(Event, Event.id == Expense.event_id)
        .where(
            Event.organization_id == organization_id,
            Member.user_id.isnot(None),
            Member.user_id.in_(uids),
        )
        .group_by(Member.user_id)
    ).all()
    exp_by = {uid: Decimal("0") for uid in uids}
    for uid, s in exp_rows:
        if uid is not None:
            exp_by[int(uid)] += Decimal(str(s or 0))

    out: list[MemberBalance] = []
    for om in oms:
        u = om.user
        uid = om.user_id
        c = contrib_by.get(uid, Decimal("0")).quantize(Decimal("0.01"))
        e = exp_by.get(uid, Decimal("0")).quantize(Decimal("0.01"))
        label = ((u.full_name or "").strip() or u.mobile) if u else str(uid)
        out.append(
            MemberBalance(
                member_id=om.id,
                user_id=uid,
                name=label,
                contributed=c,
                expended=e,
                remaining=(c - e).quantize(Decimal("0.01")),
            )
        )
    return out


def member_balances(db: Session, event_id: int) -> list[MemberBalance]:
    """Per event member: share of this event's expenses only (pool lives at org level)."""
    members = list(
        db.scalars(
            select(Member).where(Member.event_id == event_id).order_by(Member.id)
        )
    )
    if not members:
        return []

    mids = [m.id for m in members]
    z = Decimal("0").quantize(Decimal("0.01"))

    split_rows = db.execute(
        select(ExpenseSplit.member_id, ExpenseSplit.amount)
        .join(Expense)
        .where(Expense.event_id == event_id)
    ).all()
    expended: dict[int, Decimal] = {mid: Decimal("0") for mid in mids}
    for mid, amt in split_rows:
        expended[mid] += Decimal(str(amt))

    return [
        MemberBalance(
            member_id=m.id,
            user_id=m.user_id,
            name=m.name,
            contributed=z,
            expended=expended[m.id].quantize(Decimal("0.01")),
            remaining=z,
        )
        for m in members
    ]
