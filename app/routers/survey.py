import json  
import logging
from datetime import datetime
from typing import Annotated, List, Optional
from urllib.parse import quote
import uuid as uuid_lib

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, get_db_connection
from app.dependencies import (
    _compat_session_state_id,
    _guard_enumerator_web_route,
    get_signed_in_user,
)
from app.lookups import (
    _get_all_breeding_animals,
    _get_all_large_animals,
    _get_all_livestock_animals,
    _get_all_small_animals,
    _get_all_states,
)
from app.templating import templates
from app.utils import generate_formatted_id


def _insert_sync_operation(cur, operation_uuid, operation_type, record_uuid, device_uuid,
                           user_id, status, form_id=None, base_version=0,
                           result_version=None, error_message=None):
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
            operation_uuid,
            operation_type or "insert",
            record_uuid,
            device_uuid,
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
        # Table may already exist with an incompatible legacy schema; column
        # ensure below will repair it.
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


def _log_sync_operation_standalone(*args, **kwargs):
    global _sync_operations_table_ready
    c2 = cur2 = None
    try:
        c2 = get_db_connection()
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

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["survey"])


def _resolve_village_id(db, state_id, district_id, township_id, qv_id, value):
    """Return the villageID for a submitted village value.

    New forms submit villageID, but older pages/clients may still submit the
    village name. Normalise both to the ID so personcv always stores IDs.
    """
    value = str(value or "").strip()
    if not value or not all((state_id, district_id, township_id, qv_id)):
        return value
    try:
        row = db.execute(
            text("""
                SELECT villageID
                FROM village
                WHERE stateID = :state_id AND districtID = :district_id
                  AND townshipID = :township_id AND QVID = :qv_id
                  AND (villageID = :value OR LOWER(TRIM(villageName)) = LOWER(:value))
                LIMIT 1
            """),
            {
                "state_id": state_id,
                "district_id": district_id,
                "township_id": township_id,
                "qv_id": qv_id,
                "value": value,
            },
        ).mappings().first()
    except Exception as e:
        logger.warning("Village ID lookup failed for %r: %s", value, e)
        return value
    return row["villageID"] if row else value


class AnimalDataCompat(BaseModel):
    formID: str
    animalTypeID: str
    animalID: str
    speciesID: Optional[str] = None
    ageID: Optional[str] = None
    genderID: Optional[str] = None
    dataCount: int = 0


# ============================================================
# 📋 SURVEY FORM PAGES (staff / admin)
# ============================================================
@router.get("/form", response_class=HTMLResponse)
async def form_page(request: Request, db: Session = Depends(get_db)):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)
    if user["role"] == "enumerator":
        return RedirectResponse("/enumerator/part1", status_code=303)
    if user["role"] not in ("admin", "staff"):
        raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey",
        "states": _get_all_states(),
        "user": user,
        "role": user.get("role", "staff"),
        "form_id": "TEMP-FORM-ID-0001",
        "survey_prefix": "/survey",
    })


@router.get("/survey/part1")
async def survey_part1(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=303)
    if user.get("role") == "enumerator":
        return RedirectResponse("/enumerator/part1", status_code=303)

    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey",
        "states": _get_all_states(),
        "user": user,
        "role": user.get("role", "staff"),
        "form_id": "TEMP-FORM-ID-0001",
        "survey_prefix": "/survey",
    })


# ============================================================
# 🧭 STEP 1 — PERSON + LOCATION
# ============================================================
@router.post("/survey/part1")
@router.post("/enumerator/part1")
async def compat_process_step_1(
    request: Request,
    formID: Annotated[str, Form()],
    districtID: Annotated[str, Form()],
    townshipID: Annotated[str, Form()],
    qvID: Annotated[str, Form()],
    wardName: Annotated[str, Form()],
    houseHoldNo: Annotated[str, Form()],
    interviewDate: Annotated[str, Form()],
    name: Annotated[str, Form()] = "",
    gender: Annotated[str, Form()] = "",
    eduStatus: Annotated[str, Form()] = "",
    phoneNo: Annotated[str, Form()] = "",
    age: Annotated[str, Form()] = "",
    headName: Annotated[str, Form()] = "",
    headEduStatus: Annotated[str, Form()] = "",
    headGender: Annotated[str, Form()] = "",
    headPhoneNo: Annotated[str, Form()] = "",
    headAge: Annotated[str, Form()] = "",
    collection_status: Annotated[str, Form(alias="status")] = "1",
    record_uuid: Annotated[Optional[str], Form()] = None,
    db: Session = Depends(get_db),
):
    logger.info("formID from part1 %s", formID)
    enumerator_user = _guard_enumerator_web_route(request)

    # Stable id per logical survey record for idempotent saves/retries.
    cleaned_record_uuid = None
    if record_uuid:
        try:
            cleaned_record_uuid = str(uuid_lib.UUID(str(record_uuid))).lower()
        except Exception:
            cleaned_record_uuid = None
    if not cleaned_record_uuid:
        existing_uuid = request.session.get("record_uuid")
        try:
            cleaned_record_uuid = str(uuid_lib.UUID(str(existing_uuid))).lower() if existing_uuid else None
        except Exception:
            cleaned_record_uuid = None
    if not cleaned_record_uuid:
        cleaned_record_uuid = str(uuid_lib.uuid4()).lower()
    request.session["record_uuid"] = cleaned_record_uuid

    if enumerator_user:
        state_id = str(enumerator_user["stateID"])
        assigned_district = str(enumerator_user["districtID"])
        assigned_township = str(enumerator_user["townshipID"])
        if str(districtID) != assigned_district or str(townshipID) != assigned_township:
            raise HTTPException(403, "သတ်မှတ်ထားသော ခရိုင်/မြို့နယ်ကိုသာ ရွေးချယ်နိုင်ပါသည်။")

        conn_check = get_db_connection(); cur_check = conn_check.cursor()
        try:
            cur_check.execute(
                "SELECT 1 FROM qv WHERE QVID = %s AND stateID = %s "
                "AND districtID = %s AND townshipID = %s LIMIT 1",
                (qvID, state_id, assigned_district, assigned_township),
            )
            if not cur_check.fetchone():
                raise HTTPException(403, "သတ်မှတ်ထားသော မြို့နယ်အတွင်းရှိ ကျေးရွာအုပ်စု ကို ရွေးပါ။")
        finally:
            cur_check.close(); conn_check.close()
        request.session["stateID"] = state_id
    else:
        state_id = _compat_session_state_id(request)
        if not state_id:
            raise HTTPException(400, "ပြည်နယ်/တိုင်းကို အရင်ရွေးချယ်ပါ။")

    wardName = _resolve_village_id(db, state_id, districtID, townshipID, qvID, wardName)

    if collection_status not in ("0", "1"):
        raise HTTPException(400, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")
    if not enumerator_user and collection_status != "1":
        raise HTTPException(400, "ဤစာမျက်နှာမှ အချက်အလက် ကောက်ယူရန်လိုအပ်ပါသည်။")

    try:
        datetime.strptime(interviewDate, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "တွေ့ဆုံမေးမြန်းသည့်နေ့ မှန်ကန်စွာဖြည့်ပါ။")

    if not all(v.strip() for v in (wardName, houseHoldNo)):
        raise HTTPException(400, "ရပ်ကွက်/ကျေးရွာနှင့် အိမ်ထောင်စုအမှတ် ဖြည့်ပါ။")

    if collection_status == "1":
        if not all(v.strip() for v in (
            name, gender, eduStatus, phoneNo, age,
            headName, headEduStatus, headGender, headPhoneNo, headAge,
        )):
            raise HTTPException(400, "ဖြေဆိုသူနှင့် အိမ်ထောင်ဦးစီး အချက်အလက်များ ပြည့်စုံစွာဖြည့်ပါ။")
        if not age.isdigit() or not headAge.isdigit():
            raise HTTPException(400, "အသက်ကို ကိန်းဂဏန်းဖြင့် ဖြည့်ပါ။")
    else:
        name = gender = eduStatus = phoneNo = headName = headEduStatus = headGender = headPhoneNo = ""
        age = headAge = "0"
        for key in ("animals_data", "livestock_data", "breeding_animals_data",
                    "interviewer", "interviewerPhoneNo"):
            request.session.pop(key, None)

    request.session["formID"] = formID
    request.session["step1"] = {
        "status": int(collection_status),
        "districtID": districtID, "townshipID": townshipID, "qvID": qvID,
        "wardName": wardName, "houseHoldNo": houseHoldNo,
        "interviewDate": interviewDate,
        "name": name, "gender": gender, "eduStatus": eduStatus,
        "phoneNo": phoneNo, "age": age,
        "headName": headName, "headEduStatus": headEduStatus,
        "headGender": headGender, "headPhoneNo": headPhoneNo, "headAge": headAge,
    }

    if collection_status == "0":
        return await compat_submit_survey(formID, request, db)

    prefix = "/enumerator" if enumerator_user else "/survey"
    return RedirectResponse(f"{prefix}/part2/{quote(formID, safe='')}", status_code=303)


# ============================================================
# 🧭 STEP 2 — LARGE + SMALL ANIMALS
# ============================================================
@router.get("/survey/part2/{form_id}")
@router.get("/enumerator/part2/{form_id}")
async def get_survey_part2(form_id: str, request: Request):
    enumerator_user = _guard_enumerator_web_route(request)
    state_id = str(enumerator_user["stateID"]) if enumerator_user else _compat_session_state_id(request)
    request.session["formID"] = form_id
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return templates.TemplateResponse(request=request, name="FormPart2.html", context={
        "active_page": "survey",
        "largeAnimals": _get_all_large_animals(),
        "smallAnimals": _get_all_small_animals(),
        "form_id": form_id,
        "stateID": state_id,
        "states": _get_all_states(),
        "user": request.session.get("user"),
        "role": (request.session.get("user") or {}).get("role", "staff"),
        "survey_prefix": prefix,
    })


@router.post("/survey/part2/{formID}")
@router.post("/enumerator/part2/{formID}")
async def compat_process_step_2(formID: str, records: List[List[AnimalDataCompat]], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID

    large_records = records[0] if len(records) > 0 else []
    small_records = records[1] if len(records) > 1 else []

    request.session["animals_data"] = {
        "largeAnimalsTable": [item.model_dump() for item in large_records],
        "youngAnimalsTable": [item.model_dump() for item in small_records],
    }
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return JSONResponse(content={"status": "success",
                                 "redirect_url": f"{prefix}/part3/{formID}"})


# ============================================================
# 🧭 STEP 3 — POULTRY
# ============================================================
@router.get("/survey/part3/{form_id}")
@router.get("/enumerator/part3/{form_id}")
async def compat_process_step_3(form_id: str, request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = form_id
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return templates.TemplateResponse(request=request, name="FormPart3.html", context={
        "active_page": "survey",
        "livestockAni": _get_all_livestock_animals(),
        "form_id": form_id,
        "states": _get_all_states(),
        "user": request.session.get("user"),
        "role": (request.session.get("user") or {}).get("role", "staff"),
        "survey_prefix": prefix,
    })


@router.post("/survey/part4/{formID}")
@router.post("/enumerator/part4/{formID}")
async def compat_process_step_4(formID: str, data: List[AnimalDataCompat], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    request.session["livestock_data"] = jsonable_encoder(data)
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return JSONResponse(content={"status": "success",
                                 "redirect_url": f"{prefix}/part5/{formID}"})


# ============================================================
# 🧭 STEP 5 — BREEDING STOCK
# ============================================================
@router.get("/survey/part5/{formID}")
@router.get("/enumerator/part5/{formID}")
async def compat_process_part5(formID: str, request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return templates.TemplateResponse(request=request, name="FormPart4_5.html", context={
        "active_page": "survey",
        "breedingStockAni": _get_all_breeding_animals(),
        "form_id": formID,
        "states": _get_all_states(),
        "user": request.session.get("user"),
        "role": (request.session.get("user") or {}).get("role", "staff"),
        "survey_prefix": prefix,
    })


@router.post("/survey/sendForm4Data/{formID}")
@router.post("/enumerator/sendForm4Data/{formID}")
async def compat_save_breeding_data(formID: str, data: List[AnimalDataCompat], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    request.session["breeding_animals_data"] = jsonable_encoder(data)
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return JSONResponse(content={"status": "success",
                                 "redirect_url": f"{prefix}/submit/{formID}"})


@router.post("/survey/sendForm5Data/{form_id}")
@router.post("/enumerator/sendForm5Data/{form_id}")
async def compat_save_interviewer_info(form_id: str, data: dict, request: Request):
    _guard_enumerator_web_route(request)
    interviewer_name = str(data.get("name") or "").strip()
    interviewer_phone = str(data.get("phone") or "").strip()
    if not interviewer_name or not interviewer_phone:
        raise HTTPException(422, "အင်တာဗျူးကောက်ယူသူအမည်နှင့် ဖုန်းနံပါတ် ဖြည့်ပါ။")
    request.session["formID"] = form_id
    request.session["interviewer"] = interviewer_name
    request.session["interviewerPhoneNo"] = interviewer_phone
    prefix = "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"
    return JSONResponse(content={"status": "success",
                                 "redirect_url": f"{prefix}/submit/{form_id}"})


# ============================================================
# ✅ FINAL SUBMIT
# ============================================================
@router.get("/survey/submit/{formID}")
@router.get("/enumerator/submit/{formID}")
async def compat_submit_survey(
    formID: str,
    request: Request,
    db: Session = Depends(get_db),
    record_uuid: Optional[str] = Query(None),
):
    enumerator_user = _guard_enumerator_web_route(request)
    state_id = str(enumerator_user["stateID"]) if enumerator_user else _compat_session_state_id(request)

    step1 = request.session.get("step1") or {}
    session_user = request.session.get("user") or {}
    user_id = session_user.get("id")
    if user_id is None:
        raise HTTPException(400, "User session မတွေ့ပါ။ ပြန် Login လုပ်ပါ။")

    # Idempotency key: same logical record must not be duplicated on retry.
    cleaned_record_uuid = None
    raw_uuid = record_uuid or request.session.get("record_uuid")
    if raw_uuid:
        try:
            cleaned_record_uuid = str(uuid_lib.UUID(str(raw_uuid))).lower()
        except Exception:
            cleaned_record_uuid = None
    if not cleaned_record_uuid:
        cleaned_record_uuid = str(uuid_lib.uuid4()).lower()
    request.session["record_uuid"] = cleaned_record_uuid

    operation_uuid = str(uuid_lib.uuid4())
    session_device_uuid = None
    try:
        raw_device_uuid = session_user.get("device_uuid")
        session_device_uuid = str(uuid_lib.UUID(str(raw_device_uuid))).lower() if raw_device_uuid else None
    except Exception:
        session_device_uuid = None

    if enumerator_user:
        if (str(step1.get("districtID")) != str(enumerator_user["districtID"])
                or str(step1.get("townshipID")) != str(enumerator_user["townshipID"])):
            raise HTTPException(403, "Survey Location သည် Enumerator ၏ သတ်မှတ်ဧရိယာနှင့် မကိုက်ညီပါ။")

    if not state_id or not step1:
        raise HTTPException(400, "Survey အချက်အလက် မပြည့်စုံပါ။")

    # Also normalise sessions that were started before the form switched to
    # submitting villageID (e.g. an in-progress draft).
    step1["wardName"] = _resolve_village_id(
        db, state_id, step1.get("districtID"), step1.get("townshipID"),
        step1.get("qvID"), step1.get("wardName"),
    )

    collecting = step1.get("status", 1) == 1
    interviewer = request.session.get("interviewer") if collecting else ""
    interviewer_phone = request.session.get("interviewerPhoneNo") if collecting else ""
    if collecting and (not interviewer or not interviewer_phone):
        raise HTTPException(400, "အင်တာဗျူးကောက်ယူသူအချက်အလက် မရှိပါ။")

    all_animals = []
    animals_data = request.session.get("animals_data") or {}
    if isinstance(animals_data, dict):
        all_animals.extend(animals_data.get("largeAnimalsTable") or [])
        all_animals.extend(animals_data.get("youngAnimalsTable") or [])
    all_animals.extend(request.session.get("livestock_data") or [])
    all_animals.extend(request.session.get("breeding_animals_data") or [])
    if not collecting:
        all_animals = []

    conn = get_db_connection(); cur = conn.cursor()
    already_existed = False
    try:
        conn.start_transaction()

        # Idempotency: if this record_uuid was already saved (e.g. DB commit
        # succeeded but the response was lost), return success without duplicating.
        if cleaned_record_uuid:
            cur.execute(
                "SELECT formID FROM personcv WHERE record_uuid = %s LIMIT 1 FOR UPDATE",
                (cleaned_record_uuid,),
            )
            existing_by_uuid = cur.fetchone()
            if existing_by_uuid:
                formID = str(existing_by_uuid[0])
                already_existed = True
                conn.commit()
                _log_sync_operation_standalone(
                    operation_uuid, "insert", cleaned_record_uuid, session_device_uuid,
                    user_id, "conflict", formID, 0, 1,
                    "record_uuid already exists in personcv",
                )
            # fall through to response construction with already_existed=True

        if not already_existed:
            current_year = datetime.now().year
            cur.execute(
                "SELECT COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) + 1 "
                "FROM personcv WHERE formID LIKE %s FOR UPDATE",
                (f"FORM-{current_year}-%",),
            )
            row = cur.fetchone()
            next_num = int(row[0]) if row and row[0] else 1
            new_form_id = generate_formatted_id(next_num)
            logger.info("tempID=%s, generated FormID=%s (MAX-based)", formID, new_form_id)
            formID = new_form_id

            cur.execute("SELECT userId, record_uuid FROM personcv WHERE formID = %s FOR UPDATE", (formID,))
            existing_form = cur.fetchone()

            if existing_form:
                existing_user_id = existing_form[0]
                if existing_user_id is None or str(existing_user_id) != str(user_id):
                    raise HTTPException(403, "ဤ Survey Form ကို ပြင်ဆင်ခွင့်မရှိပါ။")

                cur.execute("""
                    UPDATE personcv
                    SET stateID = %s, districtID = %s, townshipID = %s, QVID = %s,
                        WardName = %s, householdNo = %s, interviewDate = %s,
                        name = %s, gender = %s, eduStatus = %s, phoneNo = %s, age = %s,
                        headName = %s, headEduStatus = %s, headGender = %s,
                        headPhoneNo = %s, headAge = %s, Interviewer = %s,
                        interviewerPhoneNo = %s, status = %s,
                        record_uuid = COALESCE(record_uuid, %s)
                    WHERE formID = %s AND userId = %s
                """, (
                    state_id, step1.get("districtID"), step1.get("townshipID"),
                    step1.get("qvID"), step1.get("wardName"), step1.get("houseHoldNo"),
                    step1.get("interviewDate"), step1.get("name"), step1.get("gender"),
                    step1.get("eduStatus"), step1.get("phoneNo"),
                    int(step1.get("age") or 0), step1.get("headName"),
                    step1.get("headEduStatus"), step1.get("headGender"),
                    step1.get("headPhoneNo"), step1.get("headAge"),
                    interviewer, interviewer_phone, int(collecting),
                    cleaned_record_uuid,
                    formID, user_id,
                ))
                if cur.rowcount == 0:
                    cur.execute("SELECT 1 FROM personcv WHERE formID = %s AND userId = %s",
                                (formID, user_id))
                    if not cur.fetchone():
                        raise HTTPException(403, "Survey Form ကို ပြင်ဆင်ခွင့်မရှိပါ။")
                cur.execute("DELETE FROM collecteddata WHERE formID = %s", (formID,))
            else:
                cur.execute("""
                    INSERT INTO personcv (
                        formID, userId, stateID, districtID, townshipID, QVID,
                        WardName, householdNo, interviewDate, name, gender, eduStatus,
                        phoneNo, age, headName, headEduStatus, headGender, headPhoneNo,
                        headAge, Interviewer, interviewerPhoneNo, status, record_uuid
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    formID, user_id, state_id, step1.get("districtID"),
                    step1.get("townshipID"), step1.get("qvID"), step1.get("wardName"),
                    step1.get("houseHoldNo"), step1.get("interviewDate"), step1.get("name"),
                    step1.get("gender"), step1.get("eduStatus"), step1.get("phoneNo"),
                    int(step1.get("age") or 0), step1.get("headName"),
                    step1.get("headEduStatus"), step1.get("headGender"),
                    step1.get("headPhoneNo"), step1.get("headAge"),
                    interviewer, interviewer_phone, int(collecting),
                    cleaned_record_uuid,
                ))

            for item in all_animals:
                cur.execute("""
                    INSERT INTO collecteddata
                        (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    formID,
                    str(item.get("animalTypeID") or ""),
                    str(item.get("animalID") or ""),
                    str(item.get("speciesID") or ""),
                    str(item.get("ageID") or ""),
                    str(item.get("genderID") or ""),
                    int(item.get("dataCount") or 0),
                ))

        if not already_existed:
            try:
                cur.execute("""
                    UPDATE householdRegister
                    SET collectionStatus = %s, updatedAt = NOW()
                    WHERE stateID = %s AND districtID = %s AND townshipID = %s
                      AND QVID = %s AND WardName = %s AND householdNo = %s
                      AND createdBy = %s
                """, (
                    "collected" if collecting else "cannot_collect",
                    state_id, step1.get("districtID"), step1.get("townshipID"),
                    step1.get("qvID"), step1.get("wardName"),
                    step1.get("houseHoldNo"), user_id,
                ))
            except Exception as e:
                logger.warning("householdRegister status update skipped: %s", e)

            conn.commit()
            _log_sync_operation_standalone(
                operation_uuid, "insert", cleaned_record_uuid, session_device_uuid,
                user_id, "commit", formID, 0, 1, None,
            )

        for key in ("stateID", "formID", "step1", "animals_data", "livestock_data",
                    "breeding_animals_data", "interviewer", "interviewerPhoneNo", "record_uuid"):
            request.session.pop(key, None)

        if already_existed:
            return {
                "status": "success",
                "already_existed": True,
                "message": "ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။",
                "formID": formID,
                "animalRecordsSaved": 0,
                "collectionStatus": int(collecting),
                "userId": user_id,
                "record_uuid": cleaned_record_uuid,
            }

        return {
            "status": "success",
            "already_existed": False,
            "message": "အချက်အလက်ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။",
            "formID": formID,
            "animalRecordsSaved": len(all_animals),
            "collectionStatus": int(collecting),
            "userId": user_id,
            "record_uuid": cleaned_record_uuid,
        }

    except HTTPException as http_err:
        try:
            conn.rollback()
        except Exception:
            pass
        _log_sync_operation_standalone(
            operation_uuid, "insert", cleaned_record_uuid, session_device_uuid,
            user_id, "rollback", formID, 0, None, getattr(http_err, "detail", str(http_err)),
        )
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Survey submit failed for formID=%s userId=%s", formID, user_id)
        _log_sync_operation_standalone(
            operation_uuid, "insert", cleaned_record_uuid, session_device_uuid,
            user_id, "rollback", formID, 0, None, str(exc)[:1000],
        )
        raise HTTPException(500, "Survey သိမ်းဆည်းမှု မအောင်မြင်ပါ။")
    finally:
        cur.close(); conn.close()


# ============================================================
# Legacy routes (keep for backwards compatibility)
# ============================================================
@router.get("/survey/part3")
async def survey_part3_get(request: Request):
    return templates.TemplateResponse(request=request, name="FormPart2.html", context={
        "active_page": "survey",
        "largeAnimals": _get_all_large_animals(),
        "smallAnimals": _get_all_small_animals(),
    })


@router.get("/survey/part4_5")
async def survey_part4_5(request: Request):
    return templates.TemplateResponse(request=request, name="FormPart4_5.html",
                                      context={"active_page": "survey"})


@router.post("/api/survey/part4")
async def submit_part4_api(request: Request, breeding_json: str = Form(...)):
    try:
        breeding = json.loads(breeding_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(400, "Invalid breeding data.")
    if not isinstance(breeding, dict):
        raise HTTPException(400, "Breeding data must be an object.")

    FORM_ID = "6"
    GENDER_MALE = "g01"
    GENDER_FEMALE = "g03"
    FIELD_MAP = {
        "local_cattle":  {"animalTypeID": "atID04", "animalID": "bsID01"},
        "local_buffalo": {"animalTypeID": "atID04", "animalID": "bsID02"},
        "dairy_buffalo": {"animalTypeID": "atID04", "animalID": "bsID03"},
        "pig":           {"animalTypeID": "atID04", "animalID": "bsID04"},
        "goat":          {"animalTypeID": "atID04", "animalID": "bsID05"},
        "sheep":         {"animalTypeID": "atID04", "animalID": "bsID06"},
    }
    rows_to_insert = []
    for key, m in FIELD_MAP.items():
        data = breeding.get(key) or {}
        if not isinstance(data, dict):
            continue
        try:
            male_n = int(data.get("male") or 0)
            female_n = int(data.get("female") or 0)
        except (ValueError, TypeError):
            continue
        if male_n > 0:
            rows_to_insert.append((FORM_ID, m["animalTypeID"], m["animalID"],
                                   None, None, GENDER_MALE, male_n))
        if female_n > 0:
            rows_to_insert.append((FORM_ID, m["animalTypeID"], m["animalID"],
                                   None, None, GENDER_FEMALE, female_n))

    if not rows_to_insert:
        raise HTTPException(400, "တိရိစ္ဆာန် အရေအတွက် အနည်းဆုံးတစ်ခု ဖြည့်ပါ။")

    conn = get_db_connection(); cur = conn.cursor()
    inserted = 0
    try:
        conn.start_transaction()
        for row in rows_to_insert:
            cur.execute("""INSERT INTO collecteddata
                           (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""", row)
            inserted += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Database error: {e}")
    finally:
        cur.close(); conn.close()

    return {"status": "success", "inserted": inserted, "formID": FORM_ID}