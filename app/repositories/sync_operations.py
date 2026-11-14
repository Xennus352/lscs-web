"""Persistence helpers for the ``sync_operations`` audit/idempotency log.

Both the web survey submit path and the offline ``/api/sync`` endpoint use the
same table. This module owns the DDL and the insert/retry logic so the two
routers do not drift apart.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.engine import Connection

from app.database import get_db_connection

logger = logging.getLogger("lbvd.sync_operations")

COLUMNS = [
    ("operation_uuid", "ALTER TABLE sync_operations ADD COLUMN operation_uuid CHAR(36) NOT NULL"),
    ("operation_type", "ALTER TABLE sync_operations ADD COLUMN operation_type VARCHAR(30) NOT NULL DEFAULT 'insert'"),
    ("record_uuid", "ALTER TABLE sync_operations ADD COLUMN record_uuid CHAR(36) NOT NULL"),
    ("device_uuid", "ALTER TABLE sync_operations ADD COLUMN device_uuid CHAR(36) DEFAULT NULL"),
    ("userID", "ALTER TABLE sync_operations ADD COLUMN userID INT DEFAULT NULL"),
    ("table_name", "ALTER TABLE sync_operations ADD COLUMN table_name VARCHAR(64) NOT NULL DEFAULT 'personcv'"),
    ("form_id", "ALTER TABLE sync_operations ADD COLUMN form_id VARCHAR(20) DEFAULT NULL"),
    ("base_version", "ALTER TABLE sync_operations ADD COLUMN base_version INT NOT NULL DEFAULT 0"),
    ("result_version", "ALTER TABLE sync_operations ADD COLUMN result_version INT DEFAULT NULL"),
    ("status", "ALTER TABLE sync_operations ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"),
    ("error_message", "ALTER TABLE sync_operations ADD COLUMN error_message TEXT DEFAULT NULL"),
    ("created_at", "ALTER TABLE sync_operations ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
]

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS sync_operations (
        operation_uuid CHAR(36) NOT NULL,
        operation_type VARCHAR(30) NOT NULL,
        record_uuid CHAR(36) NOT NULL,
        device_uuid CHAR(36) DEFAULT NULL,
        userID INT DEFAULT NULL,
        table_name VARCHAR(64) NOT NULL DEFAULT 'personcv',
        form_id VARCHAR(20) DEFAULT NULL,
        base_version INT NOT NULL DEFAULT 0,
        result_version INT DEFAULT NULL,
        status VARCHAR(20) NOT NULL,
        error_message TEXT DEFAULT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (operation_uuid),
        KEY idx_sync_op_record (record_uuid),
        KEY idx_sync_op_user (userID),
        KEY idx_sync_op_device (device_uuid),
        KEY idx_sync_op_status (status){fk}
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_FK = """,
        CONSTRAINT fk_sync_op_user FOREIGN KEY (userID)
            REFERENCES user (userID)
            ON DELETE SET NULL ON UPDATE CASCADE"""

_table_ready = False


def _clean_uuid(value):
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value))).lower()
    except (ValueError, AttributeError, TypeError):
        return None


def insert_sync_operation(
    cur,
    operation_uuid,
    operation_type,
    record_uuid,
    device_uuid,
    user_id,
    status,
    form_id=None,
    base_version=0,
    result_version=None,
    error_message=None,
) -> None:
    cur.execute(
        """
        INSERT INTO sync_operations (
            operation_uuid, operation_type, record_uuid, device_uuid, userID,
            table_name, form_id, base_version, result_version, status, error_message
        ) VALUES (%s,%s,%s,%s,%s,'personcv',%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            result_version = VALUES(result_version),
            form_id = COALESCE(VALUES(form_id), form_id),
            error_message = VALUES(error_message)
        """,
        (
            _clean_uuid(operation_uuid) or str(uuid.uuid4()),
            operation_type or "insert",
            _clean_uuid(record_uuid),
            _clean_uuid(device_uuid),
            user_id,
            form_id,
            base_version,
            result_version,
            status,
            (str(error_message)[:65535] if error_message else None),
        ),
    )


def ensure_sync_operations_table(cur) -> None:
    """Create the table using a legacy cursor (runtime self-healing path)."""
    global _table_ready
    if _table_ready:
        return
    try:
        try:
            cur.execute(_CREATE_SQL.format(fk=_FK))
        except Exception:
            cur.execute(_CREATE_SQL.format(fk=""))
    except Exception:
        # A legacy table may exist with a different shape; the column check
        # below repairs what it can.
        pass
    _table_ready = True


def ensure_sync_operations_columns(cur, conn) -> None:
    try:
        cur.execute("SHOW COLUMNS FROM sync_operations")
        existing = {row[0] for row in (cur.fetchall() or [])}
    except Exception:
        return

    changed = False
    for col, ddl in COLUMNS:
        if col in existing:
            continue
        try:
            cur.execute(ddl)
            changed = True
            logger.info("sync_operations: added missing column %s", col)
        except Exception as col_err:
            message = str(col_err).lower()
            if "duplicate" not in message and "1060" not in message:
                logger.warning(
                    "sync_operations: could not add column %s: %s", col, col_err
                )
    if changed:
        try:
            conn.commit()
        except Exception:
            pass


def ensure_sync_operations_table_engine(conn: Connection) -> None:
    """Create/upgrade the table from the FastAPI lifespan hook."""
    from sqlalchemy import inspect

    try:
        try:
            conn.exec_driver_sql(_CREATE_SQL.format(fk=_FK))
        except Exception:
            conn.exec_driver_sql(_CREATE_SQL.format(fk=""))
            logger.info("sync_operations table created without FK constraint")

        existing = {c["name"] for c in inspect(conn).get_columns("sync_operations")}
        for col, ddl in COLUMNS:
            if col in existing:
                continue
            try:
                conn.exec_driver_sql(ddl)
                logger.info("sync_operations: added missing column %s", col)
            except Exception as col_err:
                logger.warning(
                    "sync_operations: could not add column %s: %s", col, col_err
                )
    except Exception as exc:
        logger.warning("ensure_sync_operations_table: %s", exc)


def log_sync_operation_standalone(*args, conn_factory=None, **kwargs) -> None:
    """Write an audit row on a fresh connection.

    Used when the main transaction was rolled back, so the audit entry must not
    be lost together with it. ``conn_factory`` defaults to the application's
    connection factory.
    """
    global _table_ready
    factory = conn_factory or get_db_connection
    conn = cur = None
    try:
        conn = factory()
        cur = conn.cursor()
        try:
            insert_sync_operation(cur, *args, **kwargs)
        except Exception as insert_err:
            message = str(insert_err).lower()
            try:
                conn.rollback()
            except Exception:
                pass
            if "sync_operations" in message and (
                "doesn't exist" in message
                or "does not exist" in message
                or "1146" in message
                or "unknown column" in message
                or "1054" in message
            ):
                ensure_sync_operations_table(cur)
                ensure_sync_operations_columns(cur, conn)
                insert_sync_operation(cur, *args, **kwargs)
            else:
                raise
        conn.commit()
    except Exception:
        _table_ready = False
        logger.exception("Failed to write sync_operations audit row")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
