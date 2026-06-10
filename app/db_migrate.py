"""Lightweight SQLite migrations for additive columns (no Alembic)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def _add_column_if_missing(
    conn, table: str, column: str, ddl_suffix: str
) -> None:
    cols = _table_columns(conn, table)
    if column in cols:
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_suffix}"))


def run_sqlite_migrations(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        _add_column_if_missing(
            conn, "organizations", "created_by_user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn, "events", "created_by_user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn, "expenses", "created_by_user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn, "members", "created_by_user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn, "contributions", "created_by_user_id", "INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn,
            "organization_members",
            "created_by_user_id",
            "INTEGER REFERENCES users(id)",
        )

        # Backfill organizations: first membership row per org.
        conn.execute(
            text(
                """
                UPDATE organizations
                SET created_by_user_id = (
                    SELECT om.user_id
                    FROM organization_members om
                    WHERE om.organization_id = organizations.id
                    ORDER BY om.id ASC
                    LIMIT 1
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
        # Events: first linked member on that event, else first member row.
        conn.execute(
            text(
                """
                UPDATE events
                SET created_by_user_id = (
                    SELECT m.user_id
                    FROM members m
                    WHERE m.event_id = events.id AND m.user_id IS NOT NULL
                    ORDER BY m.id ASC
                    LIMIT 1
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE events
                SET created_by_user_id = (
                    SELECT m.user_id
                    FROM members m
                    WHERE m.event_id = events.id
                    ORDER BY m.id ASC
                    LIMIT 1
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE events
                SET created_by_user_id = (
                    SELECT o.created_by_user_id
                    FROM organizations o
                    WHERE o.id = events.organization_id
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
        # Only the first member row per event (bootstrap row) gets event creator; others stay NULL → event creator may manage via service helper.
        conn.execute(
            text(
                """
                UPDATE members
                SET created_by_user_id = (
                    SELECT e.created_by_user_id
                    FROM events e
                    WHERE e.id = members.event_id
                )
                WHERE created_by_user_id IS NULL
                AND NOT EXISTS (
                    SELECT 1 FROM members m2
                    WHERE m2.event_id = members.event_id AND m2.id < members.id
                )
                """
            )
        )
        # Org memberships: attribute to org creator when unknown.
        conn.execute(
            text(
                """
                UPDATE organization_members
                SET created_by_user_id = (
                    SELECT o.created_by_user_id
                    FROM organizations o
                    WHERE o.id = organization_members.organization_id
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
        # Expenses / contributions: fall back to event creator.
        conn.execute(
            text(
                """
                UPDATE expenses
                SET created_by_user_id = (
                    SELECT e.created_by_user_id
                    FROM events e
                    WHERE e.id = expenses.event_id
                )
                WHERE created_by_user_id IS NULL
                """
            )
        )
