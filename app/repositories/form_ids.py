"""Atomic ``FORM-YYYY-NNNNN`` allocation.

The old implementation used ``SELECT MAX(...) + 1 ... FOR UPDATE`` which makes
every survey submission in a year wait on the same row/gap lock. Under load
that serialises the whole form-submission path and can end in a deadlock or a
50 second lock-wait timeout.

This module keeps a small counter table instead. Allocation is still
transactional, but the lock is held for a single indexed row update only.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger("lbvd.form_ids")

SEQUENCE_TABLE = "form_sequence"


def _form_like(year: int) -> str:
    return f"FORM-{year}-%"


def ensure_form_sequence_table(conn: Connection) -> None:
    """Create and seed the counter table used by :func:`allocate_form_id`."""
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS form_sequence (
            year INT NOT NULL,
            next_val INT NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (year)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )

    # Seed the current year past any rows that were created before this table
    # existed. GREATEST keeps a value that is already further ahead.
    year = datetime.now().year
    max_value = conn.execute(
        text(
            "SELECT COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) "
            "FROM personcv WHERE formID LIKE :pattern"
        ),
        {"pattern": _form_like(year)},
    ).scalar()
    next_val = int(max_value or 0) + 1
    conn.exec_driver_sql(
        "INSERT INTO form_sequence (year, next_val) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE next_val = GREATEST(next_val, VALUES(next_val))",
        (year, next_val),
    )


def _fetch_scalar(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]


def allocate_form_id(cur, year: int | None = None, max_attempts: int = 5) -> str:
    """Reserve and return the next form ID.

    ``cur`` is the legacy cursor used by the survey/sync routers. The caller
    must be inside a transaction; the allocation participates in it so a
    rolled-back submission also gives the number back.
    """
    year = year or datetime.now().year
    pattern = _form_like(year)

    for _ in range(max_attempts):
        # Make sure a counter row exists and is at least past existing data.
        # On the very first call this reads personcv once; afterwards it is a
        # single no-op duplicate-key check.
        cur.execute(
            "INSERT INTO form_sequence (year, next_val) "
            "SELECT %s, COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) + 1 "
            "FROM personcv WHERE formID LIKE %s "
            "ON DUPLICATE KEY UPDATE year = year",
            (year, pattern),
        )
        # ``next_val`` is the value this call will hand out. LAST_INSERT_ID()
        # returns the *stored* (already incremented) value, so subtract one.
        cur.execute(
            "UPDATE form_sequence SET next_val = LAST_INSERT_ID(next_val + 1) "
            "WHERE year = %s",
            (year,),
        )
        cur.execute("SELECT LAST_INSERT_ID()")
        stored_next = _fetch_scalar(cur.fetchone())
        if stored_next in (None, 0):
            # The row disappeared between the statements; retry.
            continue

        candidate = int(stored_next) - 1
        form_id = f"FORM-{year}-{candidate:05d}"

        # The counter should already be past all existing rows, but guard
        # against manually imported data so two records never share a formID.
        cur.execute("SELECT 1 FROM personcv WHERE formID = %s LIMIT 1", (form_id,))
        if cur.fetchone() is None:
            return form_id

        logger.warning("form_sequence was behind personcv; skipping %s", form_id)

    raise RuntimeError("Could not allocate a unique form ID")
