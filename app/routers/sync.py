import logging
import time
import uuid
from datetime import datetime

from anyio import to_thread
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import DB_RETRY_ATTEMPTS, SYNC_REQUIRE_AUTH
from app.database import get_db_connection
from app.repositories.form_ids import allocate_form_id
from app.repositories.sync_operations import log_sync_operation_standalone
from app.repositories.transactions import (
    is_duplicate_record_uuid_error,
    is_retryable_error,
)

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
    """Allocate the next form ID through the shared sequence table."""
    return allocate_form_id(cur)


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


def _process_operations(operations, session_user_id, body_device_uuid):
    """Apply a sync batch. Runs in a worker thread, not on the event loop.

    The web request only parses/validates the JSON; all blocking PyMySQL work
    happens here so one large offline batch cannot freeze every other request
    served by the same Uvicorn worker.
    """
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
            ) or body_device_uuid

            # The authenticated session is authoritative; the payload userId is
            # only used by legacy clients that do not send a session yet.
            op_user_id = session_user_id if session_user_id is not None else person.get("userId")

            if not record_uuid:
                log_sync_operation_standalone(
                    operation_uuid, "insert", str(uuid.uuid4()),
                    op_device_uuid, op_user_id, "rollback", None, 0, None,
                    "record_uuid is required for idempotent sync.",
                    conn_factory=get_db_connection,
                )
                results.append(_result(
                    operation_uuid,
                    "rejected",
                    error_message="record_uuid is required for idempotent sync.",
                ))
                continue

            for attempt in range(1, DB_RETRY_ATTEMPTS + 1):
                try:
                    conn.start_transaction()

                    # Idempotency check: if this record_uuid already exists, the
                    # data was saved successfully earlier (possibly before a
                    # network/client failure).
                    cursor.execute(
                        "SELECT formID FROM personcv WHERE record_uuid = %s LIMIT 1 FOR UPDATE",
                        (record_uuid,),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        existing_form_id = _as_text(existing[0])
                        conn.commit()
                        log_sync_operation_standalone(
                            operation_uuid, "insert", record_uuid, op_device_uuid,
                            op_user_id, "conflict", existing_form_id, 0, 1,
                            "record_uuid already exists in personcv",
                            conn_factory=get_db_connection,
                        )
                        results.append(_result(
                            operation_uuid,
                            "duplicate",
                            server_form_id=existing_form_id,
                            error_message="ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။",
                        ))
                        break

                    if not _personcv_required_ok(person):
                        conn.rollback()
                        log_sync_operation_standalone(
                            operation_uuid, "insert", record_uuid, op_device_uuid,
                            op_user_id, "rollback", person.get("formID") or None, 0, None,
                            "required personcv fields missing",
                            conn_factory=get_db_connection,
                        )
                        results.append(_result(
                            operation_uuid,
                            "rejected",
                            error_message="လိုအပ်သော အချက်အလက်များ မပြည့်စုံပါ။",
                        ))
                        break

                    form_id = person.get("formID") or ""
                    if not form_id or form_id.upper().startswith("TEMP"):
                        form_id = _generate_form_id(cursor)

                    # Safety: avoid colliding with an existing formID that has no record_uuid.
                    cursor.execute("SELECT 1 FROM personcv WHERE formID = %s LIMIT 1", (form_id,))
                    if cursor.fetchone():
                        form_id = _generate_form_id(cursor)

                    user_id = session_user_id if session_user_id is not None else person.get("userId")

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
                    log_sync_operation_standalone(
                        operation_uuid, "insert", record_uuid, op_device_uuid,
                        op_user_id, "commit", form_id, 0, 1, None,
                        conn_factory=get_db_connection,
                    )
                    results.append(_result(
                        operation_uuid,
                        "accepted",
                        server_form_id=form_id,
                        server_version=1,
                        error_message="အချက်အလက်ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။",
                    ))
                    break

                except Exception as op_err:
                    if conn:
                        try:
                            conn.rollback()
                        except Exception:
                            pass

                    # Race: another request inserted the same record_uuid after
                    # our check. Treat it as idempotent success.
                    if is_duplicate_record_uuid_error(op_err):
                        existing_form_id = _lookup_form_id_by_record_uuid(record_uuid)
                        log_sync_operation_standalone(
                            operation_uuid, "insert", record_uuid,
                            op_device_uuid, op_user_id, "conflict", existing_form_id,
                            0, 1, "record_uuid already exists in personcv (race)",
                            conn_factory=get_db_connection,
                        )
                        results.append(_result(
                            operation_uuid,
                            "duplicate",
                            server_form_id=existing_form_id,
                            error_message="ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။",
                        ))
                        break

                    if is_retryable_error(op_err) and attempt < DB_RETRY_ATTEMPTS:
                        logger.warning(
                            "Sync operation %s retry %s/%s after transient error: %s",
                            operation_uuid, attempt, DB_RETRY_ATTEMPTS, op_err,
                        )
                        time.sleep(0.05 * attempt)
                        continue

                    logger.exception("Sync operation failed: %s", operation_uuid)
                    log_sync_operation_standalone(
                        operation_uuid, "insert", record_uuid,
                        op_device_uuid, op_user_id, "rollback", person.get("formID") or None,
                        0, None, str(op_err)[:1000],
                        conn_factory=get_db_connection,
                    )
                    results.append(_result(
                        operation_uuid,
                        "rejected",
                        error_message="ဆာဗာတွင် သိမ်းဆည်းရာ၌ အမှားဖြစ်ပွားပါသည်။",
                    ))
                    break

        return results

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


def _lookup_form_id_by_record_uuid(record_uuid):
    conn = cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT formID FROM personcv WHERE record_uuid = %s LIMIT 1",
            (record_uuid,),
        )
        row = cur.fetchone()
        return _as_text(row[0]) if row else None
    except Exception:
        logger.warning("Could not look up record_uuid %s", record_uuid, exc_info=True)
        return None
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
    if session_user_id is None and SYNC_REQUIRE_AUTH:
        return JSONResponse(
            {"detail": "Sync အတွက် Login လုပ်ရန် လိုအပ်ပါသည်။"},
            status_code=401,
        )

    body_device_uuid = _clean_uuid(
        body.get("device_id") or body.get("device_uuid")
        or _current_device_uuid(request, body)
    )

    # PyMySQL is synchronous; keep it off the event loop so a batch of hundreds
    # of offline records does not block login/dashboard/health-check requests.
    results = await to_thread.run_sync(
        _process_operations, operations, session_user_id, body_device_uuid
    )
    return JSONResponse({"results": results})
