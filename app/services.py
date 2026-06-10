from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, func, select
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
    Contribution,
    Event,
    Expense,
    ExpenseSplit,
    Member,
    Organization,
    OrganizationMember,
    User,
)
from app.schemas import ExpenseCreate, ExpenseSplitInput, MemberBalance


def get_user_by_mobile(db: Session, mobile: str) -> User | None:
    key = normalize_mobile(mobile)
    return db.scalar(select(User).where(User.mobile == key))


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
            joinedload(Event.members).joinedload(Member.contributions),
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
            joinedload(Event.members).joinedload(Member.contributions),
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
) -> Member:
    if not user_can_access_event(db, acting_user_id, event_id):
        raise PermissionError("You cannot edit this event.")
    uid: int | None = None
    name_stripped = (name or "").strip()
    if mobile and (m := mobile.strip()):
        u = get_user_by_mobile(db, m)
        if not u:
            raise ValueError("No user registered with that mobile number.")
        uid = u.id
        if not name_stripped:
            name_stripped = u.full_name or u.mobile
    if not name_stripped:
        raise ValueError(
            "Name is required (or provide a registered mobile to use their profile)."
        )
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


def add_contribution(
    db: Session,
    member_id: int,
    amount: Decimal,
    note: str | None,
    *,
    actor_user_id: int | None = None,
) -> Contribution:
    mem = db.get(Member, member_id)
    if not mem:
        raise ValueError("Member not found.")
    c = Contribution(
        member_id=member_id,
        amount=amount,
        note=note,
        created_by_user_id=actor_user_id,
    )
    db.add(c)
    db.flush()
    ev = db.get(Event, mem.event_id)
    if ev:
        uids = list(dict.fromkeys(event_linked_user_ids(db, mem.event_id)))
        if not uids and actor_user_id:
            uids = [actor_user_id]
        amt = f"{amount:.2f}"
        mname = mem.name
        aname = user_display_name(db, actor_user_id) if actor_user_id else "Someone"
        emit_activity(
            db,
            recipient_user_ids=uids,
            organization_id=ev.organization_id,
            event_id=ev.id,
            actor_user_id=actor_user_id,
            kind="contribution_added",
            summary=f'{aname} logged ₹{amt} to the pool for {mname} in "{ev.name}"',
        )
    db.commit()
    db.refresh(c)
    return c


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


def _can_manage_contribution(c: Contribution, acting_user_id: int, db: Session) -> bool:
    if c.created_by_user_id is not None:
        return c.created_by_user_id == acting_user_id
    mem = db.get(Member, c.member_id)
    if not mem:
        return False
    ev = db.get(Event, mem.event_id)
    return ev is not None and ev.created_by_user_id == acting_user_id


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
        u = get_user_by_mobile(db, m)
        if not u:
            raise ValueError("No user registered with that mobile number.")
        uid = u.id
        if not name_stripped:
            name_stripped = u.full_name or u.mobile
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
    n_contrib = int(
        db.scalar(
            select(func.count())
            .select_from(Contribution)
            .where(Contribution.member_id == member_id)
        )
        or 0
    )
    n_splits = int(
        db.scalar(
            select(func.count())
            .select_from(ExpenseSplit)
            .where(ExpenseSplit.member_id == member_id)
        )
        or 0
    )
    if n_contrib or n_splits:
        raise ValueError(
            "This member has pool contributions or expense splits. "
            "Remove or reassign those before deleting the member."
        )
    db.delete(mem)
    db.commit()


def update_contribution(
    db: Session,
    contribution_id: int,
    acting_user_id: int,
    *,
    amount: Decimal,
    note: str | None,
) -> Contribution:
    c = db.get(Contribution, contribution_id)
    if not c:
        raise ValueError("Contribution not found.")
    mem = db.get(Member, c.member_id)
    if not mem or not user_can_access_event(db, acting_user_id, mem.event_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_contribution(c, acting_user_id, db):
        raise PermissionError("Only the person who logged this contribution can edit it.")
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    c.amount = amount
    c.note = (note or "").strip() or None
    db.commit()
    db.refresh(c)
    return c


def delete_contribution(db: Session, contribution_id: int, acting_user_id: int) -> None:
    c = db.get(Contribution, contribution_id)
    if not c:
        raise ValueError("Contribution not found.")
    mem = db.get(Member, c.member_id)
    if not mem or not user_can_access_event(db, acting_user_id, mem.event_id):
        raise PermissionError("Not allowed.")
    if not _can_manage_contribution(c, acting_user_id, db):
        raise PermissionError("Only the person who logged this contribution can delete it.")
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


def user_can_manage_contribution(
    db: Session, contribution_id: int, acting_user_id: int
) -> bool:
    c = db.get(Contribution, contribution_id)
    if not c:
        return False
    mem = db.get(Member, c.member_id)
    if not mem or not user_can_access_event(db, acting_user_id, mem.event_id):
        return False
    return _can_manage_contribution(c, acting_user_id, db)


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
    """Across all events, totals for every event Member row linked to this user."""
    member_ids = list(
        db.scalars(select(Member.id).where(Member.user_id == user_id)).all()
    )
    z = Decimal("0").quantize(Decimal("0.01"))
    if not member_ids:
        return {
            "total_contributed": z,
            "total_expended": z,
            "total_remaining": z,
        }

    contrib_sum = db.scalar(
        select(func.coalesce(func.sum(Contribution.amount), 0)).where(
            Contribution.member_id.in_(member_ids)
        )
    )
    split_sum = db.scalar(
        select(func.coalesce(func.sum(ExpenseSplit.amount), 0)).where(
            ExpenseSplit.member_id.in_(member_ids)
        )
    )
    contributed = Decimal(str(contrib_sum or 0)).quantize(Decimal("0.01"))
    expended = Decimal(str(split_sum or 0)).quantize(Decimal("0.01"))
    remaining = (contributed - expended).quantize(Decimal("0.01"))
    return {
        "total_contributed": contributed,
        "total_expended": expended,
        "total_remaining": remaining,
    }


def member_balances(db: Session, event_id: int) -> list[MemberBalance]:
    members = list(
        db.scalars(
            select(Member).where(Member.event_id == event_id).order_by(Member.id)
        )
    )
    if not members:
        return []

    mids = [m.id for m in members]

    contrib_rows = db.execute(
        select(Contribution.member_id, Contribution.amount).where(
            Contribution.member_id.in_(mids)
        )
    ).all()
    contributed: dict[int, Decimal] = {mid: Decimal("0") for mid in mids}
    for mid, amt in contrib_rows:
        contributed[mid] += Decimal(str(amt))

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
            name=m.name,
            contributed=contributed[m.id].quantize(Decimal("0.01")),
            expended=expended[m.id].quantize(Decimal("0.01")),
            remaining=(contributed[m.id] - expended[m.id]).quantize(Decimal("0.01")),
        )
        for m in members
    ]
