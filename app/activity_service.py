"""Per-user activity feed / notifications (one row per recipient)."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, Event, Member, Organization, OrganizationMember, User


def org_member_user_ids(db: Session, organization_id: int) -> list[int]:
    return list(
        db.scalars(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == organization_id
            )
        )
    )


def event_linked_user_ids(db: Session, event_id: int) -> list[int]:
    rows = db.scalars(
        select(Member.user_id).where(
            Member.event_id == event_id,
            Member.user_id.isnot(None),
        )
    ).all()
    return [int(uid) for uid in rows if uid is not None]


def emit_activity(
    db: Session,
    *,
    recipient_user_ids: Iterable[int],
    organization_id: int | None,
    event_id: int | None,
    actor_user_id: int | None,
    kind: str,
    summary: str,
    summaries_by_user: dict[int, str] | None = None,
) -> None:
    """Append notification rows; caller must commit (same transaction as caller's changes).

    If ``summaries_by_user`` is set, each recipient uses ``summaries_by_user[uid]`` when
    present; otherwise ``summary`` is used for that user.
    """
    base = (summary or "").strip()[:500]
    seen: set[int] = set()
    for uid in recipient_user_ids:
        if uid is None:
            continue
        uid = int(uid)
        if uid in seen:
            continue
        seen.add(uid)
        if summaries_by_user is not None and uid in summaries_by_user:
            text = (summaries_by_user[uid] or "").strip()[:500]
        else:
            text = base
        db.add(
            Activity(
                recipient_user_id=uid,
                organization_id=organization_id,
                event_id=event_id,
                actor_user_id=actor_user_id,
                kind=kind,
                summary=text,
            )
        )


def count_unread(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Activity)
            .where(
                Activity.recipient_user_id == user_id,
                Activity.read_at.is_(None),
            )
        )
        or 0
    )


def list_for_user(
    db: Session, user_id: int, *, limit: int = 200
) -> list[Activity]:
    return list(
        db.scalars(
            select(Activity)
            .where(Activity.recipient_user_id == user_id)
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
    )


def list_for_org(
    db: Session, user_id: int, organization_id: int, *, limit: int = 80
) -> list[Activity]:
    return list(
        db.scalars(
            select(Activity)
            .where(
                Activity.recipient_user_id == user_id,
                Activity.organization_id == organization_id,
            )
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
    )


def list_for_event(
    db: Session, user_id: int, event_id: int, *, limit: int = 80
) -> list[Activity]:
    return list(
        db.scalars(
            select(Activity)
            .where(
                Activity.recipient_user_id == user_id,
                Activity.event_id == event_id,
            )
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
    )


def mark_read(db: Session, user_id: int, activity_id: int) -> bool:
    row = db.get(Activity, activity_id)
    if not row or row.recipient_user_id != user_id:
        return False
    row.read_at = datetime.utcnow()
    db.commit()
    return True


def mark_all_read(db: Session, user_id: int) -> int:
    rows = list(
        db.scalars(
            select(Activity).where(
                Activity.recipient_user_id == user_id,
                Activity.read_at.is_(None),
            )
        )
    )
    now = datetime.utcnow()
    for r in rows:
        r.read_at = now
    db.commit()
    return len(rows)


def user_display_name(db: Session, user_id: int | None) -> str:
    if not user_id:
        return "Someone"
    u = db.get(User, user_id)
    if not u:
        return "Someone"
    return (u.full_name or u.mobile).strip() or "User"


def group_activities_hierarchy(
    db: Session, activities: list[Activity]
) -> list[dict]:
    """Build org > event > [activity] for templates."""
    org_ids = {a.organization_id for a in activities if a.organization_id}
    event_ids = {a.event_id for a in activities if a.event_id}

    org_names: dict[int, str] = {}
    if org_ids:
        for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids))):
            org_names[o.id] = o.name

    event_meta: dict[int, tuple[int, str]] = {}
    if event_ids:
        for ev in db.scalars(select(Event).where(Event.id.in_(event_ids))):
            event_meta[ev.id] = (ev.organization_id, ev.name)

    # Preserve org order by first appearance in feed
    org_order: OrderedDict[int, None] = OrderedDict()
    for a in activities:
        oid = a.organization_id
        if oid and oid not in org_order:
            org_order[oid] = None

    out: list[dict] = []
    for oid in org_order:
        org_block: dict = {
            "organization_id": oid,
            "organization_name": org_names.get(oid, f"Org #{oid}"),
            "event_groups": OrderedDict(),
        }
        for a in activities:
            if a.organization_id != oid:
                continue
            eid = a.event_id
            key = eid if eid else 0
            if key not in org_block["event_groups"]:
                if eid:
                    _, ename = event_meta.get(eid, (oid, f"Event #{eid}"))
                    label = ename
                else:
                    label = "Organization"
                org_block["event_groups"][key] = {
                    "event_id": eid,
                    "event_name": label,
                    "activities": [],
                }
            org_block["event_groups"][key]["activities"].append(a)
        org_block["event_groups"] = list(org_block["event_groups"].values())
        out.append(org_block)
    return out


def activity_to_json(a: Activity) -> dict:
    return {
        "id": a.id,
        "organization_id": a.organization_id,
        "event_id": a.event_id,
        "actor_user_id": a.actor_user_id,
        "kind": a.kind,
        "summary": a.summary,
        "read_at": a.read_at.isoformat() if a.read_at else None,
        "created_at": a.created_at.isoformat(),
    }


def group_activities_hierarchy_json(db: Session, activities: list[Activity]) -> list[dict]:
    raw = group_activities_hierarchy(db, activities)
    out: list[dict] = []
    for ob in raw:
        evs = []
        for eg in ob["event_groups"]:
            evs.append(
                {
                    "event_id": eg["event_id"],
                    "event_name": eg["event_name"],
                    "activities": [activity_to_json(a) for a in eg["activities"]],
                }
            )
        out.append(
            {
                "organization_id": ob["organization_id"],
                "organization_name": ob["organization_name"],
                "event_groups": evs,
            }
        )
    return out
