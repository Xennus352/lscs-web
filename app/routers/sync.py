import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import get_db_connection

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["sync"])


def _clean_uuid(value):
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value))).lower()
    except (ValueError, AttributeError, TypeError):
        return None


def _as_text(value, default=""):
    if value is None:
        return default
    return str(value)


def _as_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _result(operation_uuid, status, server_form_id=None, server_version=None, error_message=None):
    return {
        "operation_uuid": operation_uuid,
        "status": status,
        "server_version": server_version,
        "server_form_id": server_form_id,
        "error_message": error_message,
    }


def _current_user_id(request: Request):
    user = request.session.get("user") or {}
    return user.get("id")


def _current_device_uuid(request: Request, body: dict = None):
    user = request.session.get("user") or {}
    value = user.get("device_uuid")
    if not value and isinstance(body, dict):
        value = body.get("device_id") or body.get("device_uuid")
    return _clean_uuid(value)


def _is_authorized(request: Request):
    # Web sessions are primary; mobile may send a bearer/cookie-based session in future.
    if _current_user_id(request) is not None:
        return True
    return False


def _insert_sync_operation(cur, operation_uuid, operation_type, record_uuid, device_uuid,
                           user_id, status, form_id=None, base_version=0,
                           result_version=None, error_message=None):
    """Insert a sync_operations audit row. Use within the same transaction for
    commit status; for rollback/conflict logging after a rollback, caller should
    execute on a fresh/autocommit cursor."""
    op_uuid = _clean_uuid(operation_uuid) or str(uuid.uuid4())
    rec_uuid = _clean_uuid(record_uuid)
    dev_uuid = _clean_uuid(device_uuid)
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
            op_uuid,
            operation_type or "insert",
            rec_uuid,
            dev_uuid,
            user_id,
            form_id,
            base_version,
            result_version,
            status,
            (str(error_message)[:65535] if error_message else None),
        ),
    )


_sync_operations_table_ready = False

_SYNC_OPERATIONS_COLUMNS = [
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


def _ensure_sync_operations_table(cur):
    global _sync_operations_table_ready
    if _sync_operations_table_ready:
        return
    try:
        cur.execute("""
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
                KEY idx_sync_op_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    except Exception:
        pass
    _sync_operations_table_ready = True


def _ensure_sync_operations_columns(cur, conn):
    try:
        cur.execute("SHOW COLUMNS FROM sync_operations")
        existing = {row[0] for row in (cur.fetchall() or [])}
    except Exception:
        return
    changed = False
    for col, ddl in _SYNC_OPERATIONS_COLUMNS:
        if col not in existing:
            try:
                cur.execute(ddl)
                changed = True
                logger.info("sync_operations: added missing column %s", col)
            except Exception as col_err:
                msg = str(col_err).lower()
                if "duplicate" not in msg and "1060" not in msg:
                    logger.warning("sync_operations: could not add column %s: %s", col, col_err)
    if changed:
        try:
            conn.commit()
        except Exception:
            pass


def _log_sync_operation_standalone(conn_factory, *args, **kwargs):
    """Log sync_operations outside a rolled-back transaction."""
    global _sync_operations_table_ready
    c2 = cur2 = None
    try:
        c2 = conn_factory()
        cur2 = c2.cursor()
        try:
            _insert_sync_operation(cur2, *args, **kwargs)
        except Exception as insert_err:
            err = str(insert_err).lower()
            try:
                c2.rollback()
            except Exception:
                pass
            if "sync_operations" in err and (
                "doesn't exist" in err or "does not exist" in err or "1146" in err
                or "unknown column" in err or "1054" in err
            ):
                _ensure_sync_operations_table(cur2)
                _ensure_sync_operations_columns(cur2, c2)
                _insert_sync_operation(cur2, *args, **kwargs)
            else:
                raise
        c2.commit()
    except Exception:
        _sync_operations_table_ready = False
        logger.exception("Failed to write sync_operations audit row")
        if c2:
            try:
                c2.rollback()
            except Exception:
                pass
    finally:
        if cur2:
            try:
                cur2.close()
            except Exception:
                pass
        if c2:
            try:
                c2.close()
            except Exception:
                pass


def _normalize_personcv_payload(payload: dict):
    """Extract personcv-compatible fields from a sync operation payload.
    Supports payload.data containing personcv fields (flat or nested under
    personcv/step1), plus common top-level aliases.
    """
    payload = payload or {}
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}

    nested = {}
    for key in ("personcv", "step1", "form", "record"):
        value = data.get(key)
        if isinstance(value, dict):
            nested.update(value)

    src = {}
    src.update(data)
    src.update(nested)

    # Allow a few alternate key names used by clients.
    aliases = {
        "state_id": "stateID", "district_id": "districtID", "township_id": "townshipID",
        "qv_id": "QVID", "qvid": "QVID", "ward_name": "WardName", "village_id": "WardName",
        "villageID": "WardName", "household_no": "householdNo", "householdNo": "householdNo",
        "interview_date": "interviewDate", "respondent_name": "name", "respondentName": "name",
        "education": "eduStatus", "edu_status": "eduStatus", "phone": "phoneNo",
        "phone_no": "phoneNo", "head_name": "headName", "head_education": "headEduStatus",
        "head_gender": "headGender", "head_phone": "headPhoneNo", "head_age": "headAge",
        "interviewer": "Interviewer", "interviewer_phone": "interviewerPhoneNo",
        "user_id": "userId",
    }
    for alt, canon in aliases.items():
        if src.get(canon) in (None, "") and src.get(alt) not in (None, ""):
            src[canon] = src[alt]

    record_uuid = _clean_uuid(
        payload.get("record_uuid") or data.get("record_uuid") or src.get("record_uuid")
    )
    return {
        "record_uuid": record_uuid,
        "formID": _as_text(
            payload.get("form_id") or data.get("form_id") or data.get("formID") or src.get("formID"),
            "",
        ).strip(),
        "userId": src.get("userId"),
        "stateID": _as_text(src.get("stateID")),
        "districtID": _as_text(src.get("districtID")),
        "townshipID": _as_text(src.get("townshipID")),
        "QVID": _as_text(src.get("QVID")),
        "WardName": _as_text(src.get("WardName")),
        "householdNo": _as_text(src.get("householdNo")),
        "interviewDate": _as_text(src.get("interviewDate")),
        "name": _as_text(src.get("name")),
        "gender": _as_text(src.get("gender")),
        "eduStatus": _as_text(src.get("eduStatus")),
        "phoneNo": _as_text(src.get("phoneNo")),
        "age": _as_int(src.get("age"), 0),
        "headName": _as_text(src.get("headName")),
        "headEduStatus": _as_text(src.get("headEduStatus")),
        "headGender": _as_text(src.get("headGender")),
        "headPhoneNo": _as_text(src.get("headPhoneNo")),
        "headAge": _as_text(src.get("headAge")),
        "Interviewer": _as_text(src.get("Interviewer")),
        "interviewerPhoneNo": _as_text(src.get("interviewerPhoneNo")),
        "status": _as_int(src.get("status"), 1),
    }


def _generate_form_id(cur):
    current_year = datetime.now().year
    cur.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) + 1 "
        "FROM personcv WHERE formID LIKE %s FOR UPDATE",
        (f"FORM-{current_year}-%",),
    )
    row = cur.fetchone()
    next_num = int(row[0]) if row and row[0] else 1
    return f"FORM-{current_year}-{str(next_num).zfill(5)}"


def _collect_animal_rows(data: dict):
    if not isinstance(data, dict):
        return []
    rows = []
    for key in (
        "all_animals", "animals", "collecteddata", "animal_records",
        "largeAnimalsTable", "youngAnimalsTable", "livestock_data",
        "breeding_animals_data",
    ):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend(value)
    animals_data = data.get("animals_data")
    if isinstance(animals_data, dict):
        for key in ("largeAnimalsTable", "youngAnimalsTable", "livestock_data", "breeding_animals_data"):
            value = animals_data.get(key)
            if isinstance(value, list):
                rows.extend(value)
    return [r for r in rows if isinstance(r, dict)]


def _personcv_required_ok(person):
    # Keep validation minimal but prevent obviously empty idempotent inserts.
    required = ("stateID", "districtID", "townshipID", "householdNo")
    return all(_as_text(person.get(k)).strip() for k in required)


@router.post("/api/sync")
async def sync_operations(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body."}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"detail": "Sync payload must be a JSON object."}, status_code=400)

    operations = body.get("operations")
    if not isinstance(operations, list):
        return JSONResponse({"detail": "'operations' must be a list."}, status_code=400)

    session_user_id = _current_user_id(request)
    body_device_uuid = _clean_uuid(body.get("device_id") or body.get("device_uuid"))
    results = []

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        for operation in operations:
            if not isinstance(operation, dict):
                continue

            raw_operation_uuid = operation.get("operation_uuid") or operation.get("operationUuid")
            operation_uuid = _clean_uuid(raw_operation_uuid) or str(uuid.uuid4())

            payload = operation.get("payload") if isinstance(operation.get("payload"), dict) else operation
            person = _normalize_personcv_payload(payload)
            record_uuid = person.get("record_uuid")
            op_device_uuid = _clean_uuid(
                payload.get("device_id") or payload.get("device_uuid") or operation.get("device_id")
            ) or body_device_uuid or _current_device_uuid(request, body)
            op_user_id = person.get("userId")
            if op_user_id in (None, ""):
                op_user_id = session_user_id

            if not record_uuid:
                _log_sync_operation_standalone(
                    get_db_connection, operation_uuid, "insert", str(uuid.uuid4()),
                    op_device_uuid, op_user_id, "rollback", None, 0, None,
                    "record_uuid is required for idempotent sync.",
                )
                results.append(_result(
                    operation_uuid,
                    "rejected",
                    error_message="record_uuid is required for idempotent sync.",
                ))
                continue

            try:
                conn.start_transaction()

                # Idempotency check: if this record_uuid already exists, the data
                # was saved successfully earlier (possibly before a network/client
                # failure). Return the "already existed" success variant and log conflict.
                cursor.execute(
                    "SELECT formID FROM personcv WHERE record_uuid = %s LIMIT 1 FOR UPDATE",
                    (record_uuid,),
                )
                existing = cursor.fetchone()
                if existing:
                    existing_form_id = _as_text(existing[0])
                    conn.commit()
                    _log_sync_operation_standalone(
                        get_db_connection, operation_uuid, "insert", record_uuid, op_device_uuid,
                        op_user_id, "conflict", existing_form_id, 0, 1,
                        "record_uuid already exists in personcv",
                    )
                    results.append(_result(
                        operation_uuid,
                        "duplicate",
                        server_form_id=existing_form_id,
                        error_message="ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။",
                    ))
                    continue

                if not _personcv_required_ok(person):
                    conn.rollback()
                    _log_sync_operation_standalone(
                        get_db_connection, operation_uuid, "insert", record_uuid, op_device_uuid,
                        op_user_id, "rollback", person.get("formID") or None, 0, None,
                        "required personcv fields missing",
                    )
                    results.append(_result(
                        operation_uuid,
                        "rejected",
                        error_message="လိုအပ်သော အချက်အလက်များ မပြည့်စုံပါ။",
                    ))
                    continue

                form_id = person.get("formID") or ""
                if not form_id or form_id.upper().startswith("TEMP"):
                    form_id = _generate_form_id(cursor)

                # Safety: avoid colliding with an existing formID that has no record_uuid.
                cursor.execute("SELECT 1 FROM personcv WHERE formID = %s LIMIT 1", (form_id,))
                if cursor.fetchone():
                    form_id = _generate_form_id(cursor)

                user_id = person.get("userId")
                if user_id in (None, ""):
                    user_id = session_user_id

                interview_date = person.get("interviewDate") or None
                if not interview_date:
                    interview_date = datetime.now().date().isoformat()

                cursor.execute(
                    """
                    INSERT INTO personcv (
                        formID, userId, stateID, districtID, townshipID, QVID,
                        WardName, householdNo, interviewDate, name, gender, eduStatus,
                        phoneNo, age, headName, headEduStatus, headGender, headPhoneNo,
                        headAge, Interviewer, interviewerPhoneNo, status, record_uuid
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    """,
                    (
                        form_id,
                        user_id,
                        person.get("stateID"),
                        person.get("districtID"),
                        person.get("townshipID"),
                        person.get("QVID"),
                        person.get("WardName"),
                        person.get("householdNo"),
                        interview_date,
                        person.get("name"),
                        person.get("gender"),
                        person.get("eduStatus"),
                        person.get("phoneNo"),
                        person.get("age"),
                        person.get("headName"),
                        person.get("headEduStatus"),
                        person.get("headGender"),
                        person.get("headPhoneNo"),
                        person.get("headAge"),
                        person.get("Interviewer"),
                        person.get("interviewerPhoneNo"),
                        person.get("status"),
                        record_uuid,
                    ),
                )

                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                for item in _collect_animal_rows(data):
                    cursor.execute(
                        """
                        INSERT INTO collecteddata
                            (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            form_id,
                            _as_text(item.get("animalTypeID") or ""),
                            _as_text(item.get("animalID") or ""),
                            _as_text(item.get("speciesID") or ""),
                            _as_text(item.get("ageID") or ""),
                            _as_text(item.get("genderID") or ""),
                            _as_int(item.get("dataCount"), 0),
                        ),
                    )

                conn.commit()
                _log_sync_operation_standalone(
                    get_db_connection, operation_uuid, "insert", record_uuid, op_device_uuid,
                    op_user_id, "commit", form_id, 0, 1, None,
                )
                results.append(_result(
                    operation_uuid,
                    "accepted",
                    server_form_id=form_id,
                    server_version=1,
                    error_message="အချက်အလက်ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။",
                ))

            except Exception as op_err:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                # Race: another request inserted same record_uuid after our check.
                # Treat as idempotent success (already existed) and log conflict.
                err_text = str(op_err).lower()
                if "duplicate" in err_text and "record_uuid" in err_text:
                    try:
                        lookup_conn = get_db_connection()
                        lookup_cur = lookup_conn.cursor()
                        try:
                            lookup_cur.execute(
                                "SELECT formID FROM personcv WHERE record_uuid = %s LIMIT 1",
                                (record_uuid,),
                            )
                            row = lookup_cur.fetchone()
                            existing_form_id = _as_text(row[0]) if row else None
                        finally:
                            lookup_cur.close()
                            lookup_conn.close()
                        _log_sync_operation_standalone(
                            get_db_connection, operation_uuid, "insert", record_uuid,
                            op_device_uuid, op_user_id, "conflict", existing_form_id,
                            0, 1, "record_uuid already exists in personcv (race)",
                        )
                        results.append(_result(
                            operation_uuid,
                            "duplicate",
                            server_form_id=existing_form_id,
                            error_message="ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။",
                        ))
                        continue
                    except Exception:
                        pass

                logger.exception("Sync operation failed: %s", operation_uuid)
                _log_sync_operation_standalone(
                    get_db_connection, operation_uuid, "insert", record_uuid,
                    op_device_uuid, op_user_id, "rollback", person.get("formID") or None,
                    0, None, str(op_err)[:1000],
                )
                results.append(_result(
                    operation_uuid,
                    "rejected",
                    error_message="ဆာဗာတွင် သိမ်းဆည်းရာ၌ အမှားဖြစ်ပွားပါသည်။",
                ))

        return JSONResponse({"results": results})

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
