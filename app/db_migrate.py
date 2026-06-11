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


def _table_exists(conn, table: str) -> bool:
    r = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchone()
    return r is not None


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
        if _table_exists(conn, "contributions"):
            _add_column_if_missing(
                conn,
                "contributions",
                "created_by_user_id",
                "INTEGER REFERENCES users(id)",
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
        # Expenses: fall back to event creator.
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

        # Org-wide pool: migrate legacy per-event contributions, then drop old table.
        if not _table_exists(conn, "organization_contributions"):
            conn.execute(
                text(
                    """
                    CREATE TABLE organization_contributions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL REFERENCES organizations(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        amount NUMERIC(12, 2) NOT NULL,
                        note TEXT,
                        created_by_user_id INTEGER REFERENCES users(id),
                        created_at DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)
                    )
                    """
                )
            )
        if _table_exists(conn, "contributions") and _table_exists(
            conn, "organization_contributions"
        ):
            n = conn.execute(
                text("SELECT COUNT(*) FROM organization_contributions")
            ).scalar()
            if n == 0:
                conn.execute(
                    text(
                        """
                        INSERT INTO organization_contributions
                            (organization_id, user_id, amount, note, created_by_user_id, created_at)
                        SELECT
                            e.organization_id,
                            COALESCE(m.user_id, e.created_by_user_id),
                            c.amount,
                            c.note,
                            c.created_by_user_id,
                            c.created_at
                        FROM contributions c
                        JOIN members m ON m.id = c.member_id
                        JOIN events e ON e.id = m.event_id
                        WHERE COALESCE(m.user_id, e.created_by_user_id) IS NOT NULL
                        """
                    )
                )
            conn.execute(text("DROP TABLE IF EXISTS contributions"))
