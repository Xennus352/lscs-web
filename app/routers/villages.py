"""Township-scoped village management.

Township users can only work inside their own state/district/township.  A
village ID is generated per QV (village tract) as v001, v002, ... and is
stored in the `village` table together with the account's location.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from io import BytesIO

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import get_db_connection
from app.dependencies import get_signed_in_user
from app.templating import templates

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["villages"])

VILLAGE_NAME_MAX = 150
VILLAGE_ID_MAX_RETRIES = 5
VILLAGE_PAGE_SIZE = 10


# ============================================================
# HELPERS
# ============================================================
def _township_scope(user: dict) -> tuple[str, str, str]:
    role = str(user.get("role") or "").strip().lower()
    if role != "township":
        raise HTTPException(403, "ဤစာမျက်နှာကို မြို့နယ်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။")

    state_id = str(user.get("stateID") or "").strip()
    district_id = str(user.get("districtID") or "").strip()
    township_id = str(user.get("townshipID") or "").strip()
    if not all((state_id, district_id, township_id)):
        raise HTTPException(403, "သင့်အကောင့်တွင် သတ်မှတ်ထားသော နယ်မြေအချက်အလက် မပြည့်စုံပါ။")
    return state_id, district_id, township_id


def _township_state(user: dict) -> str:
    """Temporary village page: township users choose district/township/QV.

    Only the state is fixed by the account; the chosen district and township
    are validated against that state by the caller.
    """
    role = str(user.get("role") or "").strip().lower()
    if role != "township":
        raise HTTPException(403, "ဤစာမျက်နှာကို မြို့နယ်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။")

    state_id = str(user.get("stateID") or "").strip()
    if not state_id:
        raise HTTPException(403, "သင့်အကောင့်တွင် သတ်မှတ်ထားသော တိုင်းဒေသကြီး/ပြည်နယ် မပြည့်စုံပါ။")
    return state_id


def _fetch_districts(cursor, state_id: str) -> list[dict]:
    cursor.execute(
        "SELECT districtID, districtName FROM district "
        "WHERE stateID = %s ORDER BY districtName",
        (state_id,),
    )
    return cursor.fetchall()


def _fetch_townships(cursor, state_id: str, district_id: str) -> list[dict]:
    cursor.execute(
        "SELECT townshipID, townshipName FROM township "
        "WHERE stateID = %s AND districtID = %s ORDER BY townshipName",
        (state_id, district_id),
    )
    return cursor.fetchall()


def _validate_district(cursor, state_id: str, district_id: str) -> dict:
    cursor.execute(
        "SELECT districtID, districtName FROM district "
        "WHERE stateID = %s AND districtID = %s LIMIT 1",
        (state_id, district_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(400, "ရွေးချယ်ထားသော ခရိုင် မမှန်ကန်ပါ။")
    return row


def _validate_township(cursor, state_id: str, district_id: str,
                       township_id: str) -> dict:
    cursor.execute(
        "SELECT townshipID, townshipName FROM township "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s LIMIT 1",
        (state_id, district_id, township_id),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(400, "ရွေးချယ်ထားသော မြို့နယ် မမှန်ကန်ပါ။")
    return row


def _normalize_village_name(raw: str) -> str:
    name = unicodedata.normalize("NFC", raw or "").strip()
    return re.sub(r"\s+", " ", name)


def _fetch_qvs(cursor, state_id: str, district_id: str, township_id: str) -> list[dict]:
    cursor.execute(
        "SELECT QVID, QVName FROM qv "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
        "ORDER BY QVName",
        (state_id, district_id, township_id),
    )
    return cursor.fetchall()


def _qv_name(cursor, state_id: str, district_id: str, township_id: str, qv_id: str):
    cursor.execute(
        "SELECT QVName FROM qv "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s AND QVID = %s "
        "LIMIT 1",
        (state_id, district_id, township_id, qv_id),
    )
    return cursor.fetchone()


def _find_duplicate_village(cursor, state_id: str, district_id: str,
                            township_id: str, qv_id: str, name: str,
                            exclude_village_id: str | None = None):
    """Return a village with the same normalized name inside the same QV."""
    sql = (
        "SELECT villageID FROM village "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s AND QVID = %s "
        "AND LOWER(TRIM(villageName)) = LOWER(%s)"
    )
    params = [state_id, district_id, township_id, qv_id, name]
    if exclude_village_id:
        sql += " AND villageID <> %s"
        params.append(exclude_village_id)
    sql += " LIMIT 1"
    cursor.execute(sql, tuple(params))
    return cursor.fetchone()


def _fetch_villages(cursor, state_id: str, district_id: str, township_id: str,
                    qv_id: str = "", limit: int | None = None,
                    offset: int = 0) -> list[dict]:
    sql = """
        SELECT v.QVID, v.villageID, v.villageName, v.districtID, v.townshipID,
               COALESCE(q.QVName, v.QVID) AS QVName
        FROM village v
        LEFT JOIN qv q
          ON q.stateID = v.stateID
         AND q.districtID = v.districtID
         AND q.townshipID = v.townshipID
         AND q.QVID = v.QVID
        WHERE v.stateID = %s AND v.districtID = %s AND v.townshipID = %s
    """
    params = [state_id, district_id, township_id]
    if qv_id:
        sql += " AND v.QVID = %s"
        params.append(qv_id)
    sql += " ORDER BY COALESCE(q.QVName, v.QVID), LENGTH(v.villageID), v.villageID"
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend((limit, offset))
    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def _count_villages(cursor, state_id: str, district_id: str, township_id: str,
                    qv_id: str = "") -> int:
    sql = (
        "SELECT COUNT(*) AS total FROM village "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s"
    )
    params = [state_id, district_id, township_id]
    if qv_id:
        sql += " AND QVID = %s"
        params.append(qv_id)
    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    return int(row["total"] or 0) if row else 0


def _next_village_id(cursor, state_id: str, district_id: str,
                     township_id: str, qv_id: str) -> str:
    # FOR UPDATE serialises ID generation when the same QV is inserted into
    # concurrently.  The retry loop in the create endpoint also covers the
    # empty-group gap-lock case.
    cursor.execute(
        "SELECT villageID FROM village "
        "WHERE stateID = %s AND districtID = %s AND townshipID = %s AND QVID = %s "
        "FOR UPDATE",
        (state_id, district_id, township_id, qv_id),
    )
    highest = 0
    for row in cursor.fetchall():
        match = re.fullmatch(r"v(\d+)", str(row.get("villageID") or ""), re.IGNORECASE)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"v{highest + 1:03d}"


# ============================================================
# PAGE
# ============================================================
@router.get("/township/villages", response_class=HTMLResponse)
async def township_villages_page(request: Request, qv: str = Query(""),
                                 page: int = Query(1, ge=1)):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = str(user.get("role") or "").strip().lower()
    if role != "township":
        raise HTTPException(403, "ဤစာမျက်နှာကို မြို့နယ်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။")

    state_id, district_id, township_id = _township_scope(user)
    selected_qv = (qv or "").strip()
    page = max(1, int(page or 1))

    conn = cursor = None
    qvs = []
    villages = []
    total_villages = 0
    filtered_total = 0
    pages = 1
    location_error = None
    db_error = None
    state_name = state_id
    district_name = district_id
    township_name = township_id

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        qvs = _fetch_qvs(cursor, state_id, district_id, township_id)
        qv_ids = {str(item["QVID"]) for item in qvs}
        if selected_qv and selected_qv not in qv_ids:
            selected_qv = ""

        filtered_total = _count_villages(
            cursor, state_id, district_id, township_id, selected_qv,
        )
        pages = max(1, (filtered_total + VILLAGE_PAGE_SIZE - 1) // VILLAGE_PAGE_SIZE)
        if page > pages:
            page = pages

        villages = _fetch_villages(
            cursor, state_id, district_id, township_id, selected_qv,
            VILLAGE_PAGE_SIZE, (page - 1) * VILLAGE_PAGE_SIZE,
        )
        total_villages = _count_villages(cursor, state_id, district_id, township_id)

        cursor.execute("SELECT stateName FROM state WHERE stateID = %s", (state_id,))
        row = cursor.fetchone()
        if row and row.get("stateName"):
            state_name = row["stateName"]

        cursor.execute(
            "SELECT districtName FROM district "
            "WHERE stateID = %s AND districtID = %s",
            (state_id, district_id),
        )
        row = cursor.fetchone()
        if row and row.get("districtName"):
            district_name = row["districtName"]

        cursor.execute(
            "SELECT townshipName FROM township "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s",
            (state_id, district_id, township_id),
        )
        row = cursor.fetchone()
        if row and row.get("townshipName"):
            township_name = row["townshipName"]
    except SQLAlchemyError:
        logger.exception("Failed to load township village page")
        db_error = "ကျေးရွာစာရင်း ရယူမရပါ။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if not qvs and not db_error:
        location_error = "သင့်အကောင့်၏ မြို့နယ်အတွင်း ကျေးရွာအုပ်စု မသတ်မှတ်ရသေးပါ။"

    return templates.TemplateResponse(
        request=request,
        name="townshipVillages.html",
        status_code=503 if db_error else 200,
        context={
            "user": user,
            "role": role,
            "active_page": "township_villages",
            "user_state_id": state_id,
            "state_id": state_id,
            "district_id": district_id,
            "township_id": township_id,
            "state_name": state_name,
            "district_name": district_name,
            "township_name": township_name,
            "region_name": township_name,
            "qvs": qvs,
            "selected_qv": selected_qv,
            "villages": villages,
            "total_villages": total_villages,
            "filtered_total": filtered_total,
            "page": page,
            "pages": pages,
            "page_size": VILLAGE_PAGE_SIZE,
            "qv_count": len(qvs),
            "location_error": location_error,
            "error": db_error,
        },
    )


# ============================================================
# TEMPORARY PAGE (township users can choose district / township / QV)
# ============================================================
@router.get("/township/temporary-village", response_class=HTMLResponse)
async def temporary_village_page(
    request: Request,
    district: str = Query(""),
    township: str = Query(""),
    qv: str = Query(""),
    page: int = Query(1, ge=1),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id = _township_state(user)
    selected_district = (district or "").strip()
    selected_township = (township or "").strip()
    selected_qv = (qv or "").strip()
    page = max(1, int(page or 1))

    conn = cursor = None
    districts = []
    townships = []
    qvs = []
    villages = []
    total_villages = 0
    filtered_total = 0
    pages = 1
    location_error = None
    db_error = None
    state_name = state_id
    district_name = selected_district
    township_name = selected_township

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT stateName FROM state WHERE stateID = %s", (state_id,))
        row = cursor.fetchone()
        if row and row.get("stateName"):
            state_name = row["stateName"]

        districts = _fetch_districts(cursor, state_id)
        district_ids = {str(item["districtID"]) for item in districts}
        if selected_district not in district_ids:
            account_district = str(user.get("districtID") or "").strip()
            selected_district = (
                account_district if account_district in district_ids
                else (str(districts[0]["districtID"]) if districts else "")
            )

        if selected_district:
            for item in districts:
                if str(item["districtID"]) == selected_district:
                    district_name = item.get("districtName") or selected_district
                    break

            townships = _fetch_townships(cursor, state_id, selected_district)
            township_ids = {str(item["townshipID"]) for item in townships}
            if selected_township not in township_ids:
                account_township = str(user.get("townshipID") or "").strip()
                selected_township = (
                    account_township if account_township in township_ids
                    else (str(townships[0]["townshipID"]) if townships else "")
                )

        if selected_township:
            for item in townships:
                if str(item["townshipID"]) == selected_township:
                    township_name = item.get("townshipName") or selected_township
                    break

            qvs = _fetch_qvs(cursor, state_id, selected_district, selected_township)
            qv_ids = {str(item["QVID"]) for item in qvs}
            if selected_qv and selected_qv not in qv_ids:
                selected_qv = ""

            filtered_total = _count_villages(
                cursor, state_id, selected_district, selected_township, selected_qv,
            )
            pages = max(1, (filtered_total + VILLAGE_PAGE_SIZE - 1) // VILLAGE_PAGE_SIZE)
            if page > pages:
                page = pages

            villages = _fetch_villages(
                cursor, state_id, selected_district, selected_township, selected_qv,
                VILLAGE_PAGE_SIZE, (page - 1) * VILLAGE_PAGE_SIZE,
            )
            total_villages = _count_villages(
                cursor, state_id, selected_district, selected_township,
            )
    except SQLAlchemyError:
        logger.exception("Failed to load temporary village page")
        db_error = "ကျေးရွာစာရင်း ရယူမရပါ။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if not db_error:
        if not districts:
            location_error = "သင့်အကောင့်၏ တိုင်းဒေသကြီး/ပြည်နယ်အတွင်း ခရိုင် မသတ်မှတ်ရသေးပါ။"
        elif not townships:
            location_error = "ရွေးချယ်ထားသော ခရိုင်အတွင်း မြို့နယ် မသတ်မှတ်ရသေးပါ။"
        elif not qvs:
            location_error = "ရွေးချယ်ထားသော မြို့နယ်အတွင်း ကျေးရွာအုပ်စု မသတ်မှတ်ရသေးပါ။"

    return templates.TemplateResponse(
        request=request,
        name="temporaryVillage.html",
        status_code=503 if db_error else 200,
        context={
            "user": user,
            "role": "township",
            "active_page": "temporary_village",
            "user_state_id": state_id,
            "state_id": state_id,
            "district_id": selected_district,
            "township_id": selected_township,
            "state_name": state_name,
            "district_name": district_name,
            "township_name": township_name,
            "region_name": township_name,
            "districts": districts,
            "townships": townships,
            "qvs": qvs,
            "selected_district": selected_district,
            "selected_township": selected_township,
            "selected_qv": selected_qv,
            "villages": villages,
            "total_villages": total_villages,
            "filtered_total": filtered_total,
            "page": page,
            "pages": pages,
            "page_size": VILLAGE_PAGE_SIZE,
            "qv_count": len(qvs),
            "location_error": location_error,
            "error": db_error,
        },
    )


@router.get("/api/township/temporary-villages/options")
async def api_temporary_village_options(
    request: Request,
    district: str = Query(""),
    township: str = Query(""),
):
    user = get_signed_in_user(request)
    state_id = _township_state(user)
    district_id = (district or "").strip()
    township_id = (township or "").strip()

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if not district_id:
            return {
                "success": True,
                "districts": _fetch_districts(cursor, state_id),
                "townships": [],
                "qvs": [],
            }

        _validate_district(cursor, state_id, district_id)
        townships = _fetch_townships(cursor, state_id, district_id)
        if not township_id:
            return {
                "success": True,
                "townships": townships,
                "qvs": [],
            }

        _validate_township(cursor, state_id, district_id, township_id)
        return {
            "success": True,
            "townships": townships,
            "qvs": _fetch_qvs(cursor, state_id, district_id, township_id),
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Failed to load temporary village options")
        raise HTTPException(500, "နယ်မြေ အချက်အလက် ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# API
# ============================================================
@router.get("/api/township/villages")
async def api_list_township_villages(request: Request, qv: str = Query(""),
                                     page: int = Query(1, ge=1)):
    user = get_signed_in_user(request)
    state_id, district_id, township_id = _township_scope(user)
    qv_id = (qv or "").strip()
    page = max(1, int(page or 1))

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if qv_id and not _qv_name(cursor, state_id, district_id, township_id, qv_id):
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        filtered_total = _count_villages(
            cursor, state_id, district_id, township_id, qv_id,
        )
        pages = max(1, (filtered_total + VILLAGE_PAGE_SIZE - 1) // VILLAGE_PAGE_SIZE)
        if page > pages:
            page = pages

        villages = _fetch_villages(
            cursor, state_id, district_id, township_id, qv_id,
            VILLAGE_PAGE_SIZE, (page - 1) * VILLAGE_PAGE_SIZE,
        )
        return {
            "success": True,
            "qv": qv_id,
            "count": len(villages),
            "total": filtered_total,
            "page": page,
            "page_size": VILLAGE_PAGE_SIZE,
            "pages": pages,
            "villages": villages,
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Failed to list township villages")
        raise HTTPException(500, "ကျေးရွာစာရင်း ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/api/township/villages")
async def api_create_township_village(
    request: Request,
    qv: str = Form(...),
    villageName: str = Form(...),
):
    user = get_signed_in_user(request)
    state_id, district_id, township_id = _township_scope(user)

    qv_id = (qv or "").strip()
    name = _normalize_village_name(villageName)

    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not name:
        raise HTTPException(400, "ကျေးရွာအမည် ထည့်သွင်းပါ။")
    if len(name) > VILLAGE_NAME_MAX:
        raise HTTPException(400, f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် မကျော်ရပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        qv_row = _qv_name(cursor, state_id, district_id, township_id, qv_id)
        if not qv_row:
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        # Village names are unique only inside the selected QV.  The same name
        # may exist under different QVs in the same township.
        duplicate = _find_duplicate_village(
            cursor, state_id, district_id, township_id, qv_id, name,
        )
        if duplicate:
            raise HTTPException(
                409,
                f"'{name}' သည် ရွေးချယ်ထားသော ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
            )

        created_id = None
        for attempt in range(VILLAGE_ID_MAX_RETRIES):
            try:
                village_id = _next_village_id(
                    cursor, state_id, district_id, township_id, qv_id,
                )
                cursor.execute(
                    "INSERT INTO village "
                    "(stateID, districtID, townshipID, QVID, villageID, villageName) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (state_id, district_id, township_id, qv_id, village_id, name),
                )
                conn.commit()
                created_id = village_id
                break
            except IntegrityError:
                conn.rollback()
                if attempt == VILLAGE_ID_MAX_RETRIES - 1:
                    logger.warning(
                        "Village ID generation collided repeatedly for %s/%s/%s/%s",
                        state_id, district_id, township_id, qv_id,
                    )
                    raise HTTPException(
                        409,
                        "ကျေးရွာ ID ထုတ်ပေးရာတွင် အခြားအသုံးပြုသူနှင့် ထပ်နေပါသည်။ ပြန်လည်ကြိုးစားပါ။",
                    )

        qv_name = qv_row.get("QVName") or qv_id
        logger.info(
            "Village created: %s/%s/%s/%s/%s by %s",
            state_id, district_id, township_id, qv_id, created_id,
            user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{name}' ကျေးရွာကို အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။",
            "village": {
                "QVID": qv_id,
                "QVName": qv_name,
                "villageID": created_id,
                "villageName": name,
            },
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to create township village")
        raise HTTPException(500, "ကျေးရွာ ထည့်သွင်းရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/api/township/villages/{qv_id}/{village_id}")
async def api_update_township_village(
    request: Request,
    qv_id: str,
    village_id: str,
    qv: str = Form(...),
    villageName: str = Form(...),
):
    user = get_signed_in_user(request)
    state_id, district_id, township_id = _township_scope(user)

    old_qv_id = (qv_id or "").strip()
    old_village_id = (village_id or "").strip()
    new_qv_id = (qv or "").strip()
    name = _normalize_village_name(villageName)

    if not new_qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not name:
        raise HTTPException(400, "ကျေးရွာအမည် ထည့်သွင်းပါ။")
    if len(name) > VILLAGE_NAME_MAX:
        raise HTTPException(400, f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် မကျော်ရပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT villageID, QVID, villageName FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s LIMIT 1 FOR UPDATE",
            (state_id, district_id, township_id, old_qv_id, old_village_id),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "ပြင်ဆင်မည့် ကျေးရွာ မတွေ့ပါ။")

        qv_row = _qv_name(cursor, state_id, district_id, township_id, new_qv_id)
        if not qv_row:
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        moving_qv = new_qv_id != old_qv_id
        duplicate = _find_duplicate_village(
            cursor, state_id, district_id, township_id, new_qv_id, name,
            None if moving_qv else old_village_id,
        )
        if duplicate:
            raise HTTPException(
                409,
                f"'{name}' သည် ရွေးချယ်ထားသော ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
            )

        updated_id = old_village_id
        if moving_qv:
            for attempt in range(VILLAGE_ID_MAX_RETRIES):
                try:
                    updated_id = _next_village_id(
                        cursor, state_id, district_id, township_id, new_qv_id,
                    )
                    cursor.execute(
                        "UPDATE village SET QVID = %s, villageID = %s, villageName = %s "
                        "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
                        "AND QVID = %s AND villageID = %s",
                        (
                            new_qv_id, updated_id, name,
                            state_id, district_id, township_id,
                            old_qv_id, old_village_id,
                        ),
                    )
                    conn.commit()
                    break
                except IntegrityError:
                    conn.rollback()
                    if attempt == VILLAGE_ID_MAX_RETRIES - 1:
                        logger.warning(
                            "Village ID generation collided repeatedly while moving %s/%s/%s/%s/%s",
                            state_id, district_id, township_id,
                            old_qv_id, old_village_id,
                        )
                        raise HTTPException(
                            409,
                            "ကျေးရွာအုပ်စုသို့ ရွှေ့ရာတွင် ကျေးရွာ ID ထပ်နေပါသည်။ ပြန်လည်ကြိုးစားပါ။",
                        )
        else:
            cursor.execute(
                "UPDATE village SET villageName = %s "
                "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
                "AND QVID = %s AND villageID = %s",
                (
                    name,
                    state_id, district_id, township_id,
                    old_qv_id, old_village_id,
                ),
            )
            conn.commit()

        qv_name = qv_row.get("QVName") or new_qv_id
        logger.info(
            "Village updated: %s/%s/%s/%s/%s -> %s/%s by %s",
            state_id, district_id, township_id, old_qv_id, old_village_id,
            new_qv_id, updated_id, user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{name}' ကျေးရွာ အချက်အလက်ကို အောင်မြင်စွာ ပြင်ဆင်ပြီးပါပြီ။",
            "village": {
                "QVID": new_qv_id,
                "QVName": qv_name,
                "villageID": updated_id,
                "villageName": name,
            },
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to update township village")
        raise HTTPException(500, "ကျေးရွာ ပြင်ဆင်ရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/api/township/villages/{qv_id}/{village_id}")
async def api_delete_township_village(
    request: Request,
    qv_id: str,
    village_id: str,
):
    user = get_signed_in_user(request)
    state_id, district_id, township_id = _township_scope(user)

    qv_id = (qv_id or "").strip()
    village_id = (village_id or "").strip()
    if not qv_id or not village_id:
        raise HTTPException(400, "ကျေးရွာ အချက်အလက် မပြည့်စုံပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT villageName FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s LIMIT 1",
            (state_id, district_id, township_id, qv_id, village_id),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "ဖျက်မည့် ကျေးရွာ မတွေ့ပါ။")

        cursor.execute(
            "DELETE FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s",
            (state_id, district_id, township_id, qv_id, village_id),
        )
        conn.commit()

        village_name = existing.get("villageName") or village_id
        logger.info(
            "Village deleted: %s/%s/%s/%s/%s by %s",
            state_id, district_id, township_id, qv_id, village_id,
            user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{village_name}' ကျေးရွာကို ဖျက်ပြီးပါပြီ။",
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to delete township village")
        raise HTTPException(500, "ကျေးရွာ ဖျက်ရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# TEMPORARY VILLAGE API
# ============================================================
@router.get("/api/township/temporary-villages")
async def api_list_temporary_villages(
    request: Request,
    district: str = Query(""),
    township: str = Query(""),
    qv: str = Query(""),
    page: int = Query(1, ge=1),
):
    user = get_signed_in_user(request)
    state_id = _township_state(user)
    district_id = (district or "").strip()
    township_id = (township or "").strip()
    qv_id = (qv or "").strip()
    page = max(1, int(page or 1))

    if not district_id:
        raise HTTPException(400, "ခရိုင် တစ်ခု ရွေးချယ်ပါ။")
    if not township_id:
        raise HTTPException(400, "မြို့နယ် တစ်ခု ရွေးချယ်ပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        _validate_district(cursor, state_id, district_id)
        _validate_township(cursor, state_id, district_id, township_id)
        if qv_id and not _qv_name(cursor, state_id, district_id, township_id, qv_id):
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        filtered_total = _count_villages(
            cursor, state_id, district_id, township_id, qv_id,
        )
        total_all = _count_villages(
            cursor, state_id, district_id, township_id,
        )
        qv_count = len(_fetch_qvs(cursor, state_id, district_id, township_id))
        pages = max(1, (filtered_total + VILLAGE_PAGE_SIZE - 1) // VILLAGE_PAGE_SIZE)
        if page > pages:
            page = pages

        villages = _fetch_villages(
            cursor, state_id, district_id, township_id, qv_id,
            VILLAGE_PAGE_SIZE, (page - 1) * VILLAGE_PAGE_SIZE,
        )
        return {
            "success": True,
            "district": district_id,
            "township": township_id,
            "qv": qv_id,
            "count": len(villages),
            "total": filtered_total,
            "total_all": total_all,
            "qv_count": qv_count,
            "page": page,
            "page_size": VILLAGE_PAGE_SIZE,
            "pages": pages,
            "villages": villages,
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Failed to list temporary villages")
        raise HTTPException(500, "ကျေးရွာစာရင်း ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/api/township/temporary-villages")
async def api_create_temporary_village(
    request: Request,
    district: str = Form(...),
    township: str = Form(...),
    qv: str = Form(...),
    villageName: str = Form(...),
):
    user = get_signed_in_user(request)
    state_id = _township_state(user)

    district_id = (district or "").strip()
    township_id = (township or "").strip()
    qv_id = (qv or "").strip()
    name = _normalize_village_name(villageName)

    if not district_id:
        raise HTTPException(400, "ခရိုင် တစ်ခု ရွေးချယ်ပါ။")
    if not township_id:
        raise HTTPException(400, "မြို့နယ် တစ်ခု ရွေးချယ်ပါ။")
    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not name:
        raise HTTPException(400, "ကျေးရွာအမည် ထည့်သွင်းပါ။")
    if len(name) > VILLAGE_NAME_MAX:
        raise HTTPException(400, f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် မကျော်ရပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        _validate_district(cursor, state_id, district_id)
        _validate_township(cursor, state_id, district_id, township_id)
        qv_row = _qv_name(cursor, state_id, district_id, township_id, qv_id)
        if not qv_row:
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        duplicate = _find_duplicate_village(
            cursor, state_id, district_id, township_id, qv_id, name,
        )
        if duplicate:
            raise HTTPException(
                409,
                f"'{name}' သည် ရွေးချယ်ထားသော ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
            )

        created_id = None
        for attempt in range(VILLAGE_ID_MAX_RETRIES):
            try:
                village_id = _next_village_id(
                    cursor, state_id, district_id, township_id, qv_id,
                )
                cursor.execute(
                    "INSERT INTO village "
                    "(stateID, districtID, townshipID, QVID, villageID, villageName) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (state_id, district_id, township_id, qv_id, village_id, name),
                )
                conn.commit()
                created_id = village_id
                break
            except IntegrityError:
                conn.rollback()
                if attempt == VILLAGE_ID_MAX_RETRIES - 1:
                    logger.warning(
                        "Temporary village ID generation collided repeatedly for %s/%s/%s/%s",
                        state_id, district_id, township_id, qv_id,
                    )
                    raise HTTPException(
                        409,
                        "ကျေးရွာ ID ထုတ်ပေးရာတွင် အခြားအသုံးပြုသူနှင့် ထပ်နေပါသည်။ ပြန်လည်ကြိုးစားပါ။",
                    )

        if created_id is None:
            raise HTTPException(500, "ကျေးရွာ ထည့်သွင်းရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")

        qv_name = qv_row.get("QVName") or qv_id
        logger.info(
            "Temporary village created: %s/%s/%s/%s/%s by %s",
            state_id, district_id, township_id, qv_id, created_id,
            user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{name}' ကျေးရွာကို အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။",
            "village": {
                "districtID": district_id,
                "townshipID": township_id,
                "QVID": qv_id,
                "QVName": qv_name,
                "villageID": created_id,
                "villageName": name,
            },
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to create temporary village")
        raise HTTPException(500, "ကျေးရွာ ထည့်သွင်းရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put(
    "/api/township/temporary-villages/{district_id}/{township_id}/{qv_id}/{village_id}"
)
async def api_update_temporary_village(
    request: Request,
    district_id: str,
    township_id: str,
    qv_id: str,
    village_id: str,
    qv: str = Form(...),
    villageName: str = Form(...),
):
    user = get_signed_in_user(request)
    state_id = _township_state(user)

    district_id = (district_id or "").strip()
    township_id = (township_id or "").strip()
    old_qv_id = (qv_id or "").strip()
    old_village_id = (village_id or "").strip()
    new_qv_id = (qv or "").strip()
    name = _normalize_village_name(villageName)

    if not district_id or not township_id:
        raise HTTPException(400, "ခရိုင် နှင့် မြို့နယ် အချက်အလက် မပြည့်စုံပါ။")
    if not new_qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not name:
        raise HTTPException(400, "ကျေးရွာအမည် ထည့်သွင်းပါ။")
    if len(name) > VILLAGE_NAME_MAX:
        raise HTTPException(400, f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် မကျော်ရပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        _validate_district(cursor, state_id, district_id)
        _validate_township(cursor, state_id, district_id, township_id)

        cursor.execute(
            "SELECT villageID, QVID, villageName FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s LIMIT 1",
            (state_id, district_id, township_id, old_qv_id, old_village_id),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "ပြင်ဆင်မည့် ကျေးရွာ မတွေ့ပါ။")

        qv_row = _qv_name(cursor, state_id, district_id, township_id, new_qv_id)
        if not qv_row:
            raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

        moving_qv = new_qv_id != old_qv_id
        duplicate = _find_duplicate_village(
            cursor, state_id, district_id, township_id, new_qv_id, name,
            None if moving_qv else old_village_id,
        )
        if duplicate:
            raise HTTPException(
                409,
                f"'{name}' သည် ရွေးချယ်ထားသော ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
            )

        updated_id = old_village_id
        if moving_qv:
            for attempt in range(VILLAGE_ID_MAX_RETRIES):
                try:
                    updated_id = _next_village_id(
                        cursor, state_id, district_id, township_id, new_qv_id,
                    )
                    cursor.execute(
                        "UPDATE village SET QVID = %s, villageID = %s, villageName = %s "
                        "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
                        "AND QVID = %s AND villageID = %s",
                        (
                            new_qv_id, updated_id, name,
                            state_id, district_id, township_id,
                            old_qv_id, old_village_id,
                        ),
                    )
                    conn.commit()
                    break
                except IntegrityError:
                    conn.rollback()
                    if attempt == VILLAGE_ID_MAX_RETRIES - 1:
                        logger.warning(
                            "Temporary village ID collided while moving %s/%s/%s/%s/%s",
                            state_id, district_id, township_id,
                            old_qv_id, old_village_id,
                        )
                        raise HTTPException(
                            409,
                            "ကျေးရွာအုပ်စုသို့ ရွှေ့ရာတွင် ကျေးရွာ ID ထပ်နေပါသည်။ ပြန်လည်ကြိုးစားပါ။",
                        )
        else:
            cursor.execute(
                "UPDATE village SET villageName = %s "
                "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
                "AND QVID = %s AND villageID = %s",
                (
                    name,
                    state_id, district_id, township_id,
                    old_qv_id, old_village_id,
                ),
            )
            conn.commit()

        qv_name = qv_row.get("QVName") or new_qv_id
        logger.info(
            "Temporary village updated: %s/%s/%s/%s/%s -> %s/%s by %s",
            state_id, district_id, township_id, old_qv_id, old_village_id,
            new_qv_id, updated_id, user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{name}' ကျေးရွာ အချက်အလက်ကို အောင်မြင်စွာ ပြင်ဆင်ပြီးပါပြီ။",
            "village": {
                "districtID": district_id,
                "townshipID": township_id,
                "QVID": new_qv_id,
                "QVName": qv_name,
                "villageID": updated_id,
                "villageName": name,
            },
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to update temporary village")
        raise HTTPException(500, "ကျေးရွာ ပြင်ဆင်ရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete(
    "/api/township/temporary-villages/{district_id}/{township_id}/{qv_id}/{village_id}"
)
async def api_delete_temporary_village(
    request: Request,
    district_id: str,
    township_id: str,
    qv_id: str,
    village_id: str,
):
    user = get_signed_in_user(request)
    state_id = _township_state(user)

    district_id = (district_id or "").strip()
    township_id = (township_id or "").strip()
    qv_id = (qv_id or "").strip()
    village_id = (village_id or "").strip()
    if not all((district_id, township_id, qv_id, village_id)):
        raise HTTPException(400, "ကျေးရွာ အချက်အလက် မပြည့်စုံပါ။")

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        _validate_district(cursor, state_id, district_id)
        _validate_township(cursor, state_id, district_id, township_id)

        cursor.execute(
            "SELECT villageName FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s LIMIT 1",
            (state_id, district_id, township_id, qv_id, village_id),
        )
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(404, "ဖျက်မည့် ကျေးရွာ မတွေ့ပါ။")

        cursor.execute(
            "DELETE FROM village "
            "WHERE stateID = %s AND districtID = %s AND townshipID = %s "
            "AND QVID = %s AND villageID = %s",
            (state_id, district_id, township_id, qv_id, village_id),
        )
        conn.commit()

        village_name = existing.get("villageName") or village_id
        logger.info(
            "Temporary village deleted: %s/%s/%s/%s/%s by %s",
            state_id, district_id, township_id, qv_id, village_id,
            user.get("loginName", "?"),
        )
        return {
            "success": True,
            "message": f"'{village_name}' ကျေးရွာကို ဖျက်ပြီးပါပြီ။",
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Failed to delete temporary village")
        raise HTTPException(500, "ကျေးရွာ ဖျက်ရာတွင် အမှားဖြစ်ပေါ်ပါသည်။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# EXCEL TEMPLATE & IMPORT
# ============================================================
IMPORT_SHEET_TITLE = "Villages"
IMPORT_HEADER_NAME = "villageName"
IMPORT_HEADER_NO = "No."
IMPORT_HEADER_NO_ALIASES = {"no.", "no"}


@router.get("/api/township/villages/sample-excel")
async def api_download_sample_village_excel(request: Request):
    """Download the two-column Excel template used by the importer."""
    user = get_signed_in_user(request)
    _township_scope(user)

    wb = Workbook()
    ws = wb.active
    ws.title = IMPORT_SHEET_TITLE
    ws.append([IMPORT_HEADER_NO, IMPORT_HEADER_NAME])
    ws.append([1, "ကန်ရိုးကျေးရွာ"])
    ws.append([2, "ဆံပင်ကျေးရွာ"])
    ws.append([3, "မြို့လယ်ကျေးရွာ"])
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 32

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="sample_villages.xlsx"'
        },
    )


@router.post("/api/township/villages/import-excel")
async def api_import_township_villages_excel(request: Request):
    """Import villages from a one-sheet, at-most-two-column Excel file.

    Every inserted row reuses the account's state/district/township and the
    QV chosen in the upload form.  Rows whose village name is blank, too long
    or already present inside the same QV are skipped and reported back.
    """
    user = get_signed_in_user(request)
    state_id, district_id, township_id = _township_scope(user)

    form = await request.form()
    upload = form.get("file")
    qv_id = str(form.get("qv") or "").strip()

    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not upload or not getattr(upload, "filename", ""):
        raise HTTPException(400, "Excel ဖိုင်ကို ရွေးချယ်ပါ။")

    filename = str(upload.filename or "")
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Excel ဖိုင်ကို .xlsx ပုံစံဖြင့်သာ ရွေးချယ်ပါ။")

    content = await upload.read()
    try:
        await upload.close()
    except Exception:
        pass
    if not content:
        raise HTTPException(400, "ရွေးချယ်ထားသော Excel ဖိုင် ဗလာဖြစ်နေပါသည်။")

    try:
        wb = load_workbook(BytesIO(content), data_only=True)
    except Exception:
        logger.warning("Invalid Excel upload for village import: %s", filename)
        raise HTTPException(
            400,
            "Excel ဖိုင်ကို ဖတ်၍မရပါ။ မှန်ကန်သော .xlsx ဖိုင်ဖြစ်ကြောင်း စစ်ဆေးပါ။",
        )

    try:
        if len(wb.sheetnames) != 1:
            raise HTTPException(
                400,
                "Excel ဖိုင်တွင် စာမျက်နှာ (sheet) တစ်ခုသာ ပါဝင်ရပါမည်။",
            )

        ws = wb[wb.sheetnames[0]]
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        if not rows:
            raise HTTPException(400, "Excel ဖိုင်တွင် ဒေတာ မပါဝင်ပါ။")

        headers = [
            str(value).strip() if value is not None else ""
            for value in rows[0]
        ]
        # Trim trailing empty header cells so stray formatting does not count.
        while headers and headers[-1] == "":
            headers.pop()

        if not headers:
            raise HTTPException(400, "Excel ဖိုင်၏ ပထမတန်းတွင် ကော်လံခေါင်းစဉ် မပါဝင်ပါ။")
        if len(headers) > 2:
            raise HTTPException(
                400,
                "Excel ဖိုင်တွင် ကော်လံ နှစ်ခုထက် မပိုရပါ။ (No. နှင့် villageName)",
            )
        if headers.count(IMPORT_HEADER_NAME) != 1:
            raise HTTPException(
                400,
                "'villageName' ကော်လံ တစ်ခုတည်း အတိအကျ ပါဝင်ရပါမည်။",
            )

        name_idx = headers.index(IMPORT_HEADER_NAME)
        if len(headers) == 2:
            first_header = headers[0].strip().lower()
            if name_idx != 1 or first_header not in IMPORT_HEADER_NO_ALIASES:
                raise HTTPException(
                    400,
                    "ကော်လံ နှစ်ခုရှိပါက ပထမကော်လံမှာ 'No.' နှင့် "
                    "ဒုတိယကော်လံမှာ 'villageName' ဖြစ်ရပါမည်။",
                )

        conn = cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            qv_row = _qv_name(cursor, state_id, district_id, township_id, qv_id)
            if not qv_row:
                raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

            inserted = 0
            skipped: list[dict] = []

            for row_number, row in enumerate(rows[1:], start=2):
                if not row or all(
                    cell is None or str(cell).strip() == "" for cell in row
                ):
                    continue

                raw_name = row[name_idx] if name_idx < len(row) else None
                if raw_name is None or str(raw_name).strip() == "":
                    skipped.append({
                        "row": row_number,
                        "villageName": "",
                        "reason": "ကျေးရွာအမည် ဗလာဖြစ်နေပါသည်။",
                    })
                    continue

                name = _normalize_village_name(str(raw_name))
                if not name:
                    skipped.append({
                        "row": row_number,
                        "villageName": str(raw_name),
                        "reason": "ကျေးရွာအမည် ဗလာဖြစ်နေပါသည်။",
                    })
                    continue
                if len(name) > VILLAGE_NAME_MAX:
                    skipped.append({
                        "row": row_number,
                        "villageName": name,
                        "reason": (
                            f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် "
                            "မကျော်ရပါ။"
                        ),
                    })
                    continue

                if _find_duplicate_village(
                    cursor, state_id, district_id, township_id, qv_id, name,
                ):
                    skipped.append({
                        "row": row_number,
                        "villageName": name,
                        "reason": "ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
                    })
                    continue

                village_id = _next_village_id(
                    cursor, state_id, district_id, township_id, qv_id,
                )
                cursor.execute(
                    "INSERT INTO village "
                    "(stateID, districtID, townshipID, QVID, villageID, villageName) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (state_id, district_id, township_id, qv_id, village_id, name),
                )
                inserted += 1

            conn.commit()

            logger.info(
                "Villages imported: %s/%s/%s/%s inserted=%d skipped=%d by %s",
                state_id, district_id, township_id, qv_id,
                inserted, len(skipped), user.get("loginName", "?"),
            )

            message = f"ကျေးရွာ {inserted} ခု ထည့်သွင်းပြီးပါပြီ။"
            if skipped:
                message += f" ကျေးရွာ {len(skipped)} ခုကို ကျော်လိုက်ပါသည်။"

            return {
                "success": True,
                "message": message,
                "inserted": inserted,
                "skipped": len(skipped),
                "errors": skipped,
            }
        except HTTPException:
            raise
        except SQLAlchemyError:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.exception("Failed to import township villages from Excel")
            raise HTTPException(
                500, "Excel မှ ကျေးရွာများ ထည့်သွင်းရာတွင် အမှားဖြစ်ပေါ်ပါသည်။"
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    finally:
        try:
            wb.close()
        except Exception:
            pass


# ============================================================
# TEMPORARY EXCEL TEMPLATE & IMPORT
# ============================================================
@router.get("/api/township/temporary-villages/sample-excel")
async def api_download_temporary_sample_village_excel(request: Request):
    """Download the same two-column template used by the temporary page."""
    user = get_signed_in_user(request)
    _township_state(user)

    wb = Workbook()
    ws = wb.active
    ws.title = IMPORT_SHEET_TITLE
    ws.append([IMPORT_HEADER_NO, IMPORT_HEADER_NAME])
    ws.append([1, "ကန်ရိုးကျေးရွာ"])
    ws.append([2, "ဆံပင်ကျေးရွာ"])
    ws.append([3, "မြို့လယ်ကျေးရွာ"])
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 32

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="sample_villages.xlsx"'
        },
    )


@router.post("/api/township/temporary-villages/import-excel")
async def api_import_temporary_villages_excel(request: Request):
    """Import villages into the district/township/QV chosen in the form."""
    user = get_signed_in_user(request)
    state_id = _township_state(user)

    form = await request.form()
    upload = form.get("file")
    district_id = str(form.get("district") or "").strip()
    township_id = str(form.get("township") or "").strip()
    qv_id = str(form.get("qv") or "").strip()

    if not district_id:
        raise HTTPException(400, "ခရိုင် တစ်ခု ရွေးချယ်ပါ။")
    if not township_id:
        raise HTTPException(400, "မြို့နယ် တစ်ခု ရွေးချယ်ပါ။")
    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု တစ်ခု ရွေးချယ်ပါ။")
    if not upload or not getattr(upload, "filename", ""):
        raise HTTPException(400, "Excel ဖိုင်ကို ရွေးချယ်ပါ။")

    filename = str(upload.filename or "")
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Excel ဖိုင်ကို .xlsx ပုံစံဖြင့်သာ ရွေးချယ်ပါ။")

    content = await upload.read()
    try:
        await upload.close()
    except Exception:
        pass
    if not content:
        raise HTTPException(400, "ရွေးချယ်ထားသော Excel ဖိုင် ဗလာဖြစ်နေပါသည်။")

    try:
        wb = load_workbook(BytesIO(content), data_only=True)
    except Exception:
        logger.warning("Invalid Excel upload for temporary village import: %s", filename)
        raise HTTPException(
            400,
            "Excel ဖိုင်ကို ဖတ်၍မရပါ။ မှန်ကန်သော .xlsx ဖိုင်ဖြစ်ကြောင်း စစ်ဆေးပါ။",
        )

    try:
        if len(wb.sheetnames) != 1:
            raise HTTPException(
                400,
                "Excel ဖိုင်တွင် စာမျက်နှာ (sheet) တစ်ခုသာ ပါဝင်ရပါမည်။",
            )

        ws = wb[wb.sheetnames[0]]
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        if not rows:
            raise HTTPException(400, "Excel ဖိုင်တွင် ဒေတာ မပါဝင်ပါ။")

        headers = [
            str(value).strip() if value is not None else ""
            for value in rows[0]
        ]
        while headers and headers[-1] == "":
            headers.pop()

        if not headers:
            raise HTTPException(400, "Excel ဖိုင်၏ ပထမတန်းတွင် ကော်လံခေါင်းစဉ် မပါဝင်ပါ။")
        if len(headers) > 2:
            raise HTTPException(
                400,
                "Excel ဖိုင်တွင် ကော်လံ နှစ်ခုထက် မပိုရပါ။ (No. နှင့် villageName)",
            )
        if headers.count(IMPORT_HEADER_NAME) != 1:
            raise HTTPException(
                400,
                "'villageName' ကော်လံ တစ်ခုတည်း အတိအကျ ပါဝင်ရပါမည်။",
            )

        name_idx = headers.index(IMPORT_HEADER_NAME)
        if len(headers) == 2:
            first_header = headers[0].strip().lower()
            if name_idx != 1 or first_header not in IMPORT_HEADER_NO_ALIASES:
                raise HTTPException(
                    400,
                    "ကော်လံ နှစ်ခုရှိပါက ပထမကော်လံမှာ 'No.' နှင့် "
                    "ဒုတိယကော်လံမှာ 'villageName' ဖြစ်ရပါမည်။",
                )

        conn = cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            _validate_district(cursor, state_id, district_id)
            _validate_township(cursor, state_id, district_id, township_id)
            qv_row = _qv_name(cursor, state_id, district_id, township_id, qv_id)
            if not qv_row:
                raise HTTPException(400, "ရွေးချယ်ထားသော ကျေးရွာအုပ်စု မမှန်ကန်ပါ။")

            inserted = 0
            skipped: list[dict] = []

            for row_number, row in enumerate(rows[1:], start=2):
                if not row or all(
                    cell is None or str(cell).strip() == "" for cell in row
                ):
                    continue

                raw_name = row[name_idx] if name_idx < len(row) else None
                if raw_name is None or str(raw_name).strip() == "":
                    skipped.append({
                        "row": row_number,
                        "villageName": "",
                        "reason": "ကျေးရွာအမည် ဗလာဖြစ်နေပါသည်။",
                    })
                    continue

                name = _normalize_village_name(str(raw_name))
                if not name:
                    skipped.append({
                        "row": row_number,
                        "villageName": str(raw_name),
                        "reason": "ကျေးရွာအမည် ဗလာဖြစ်နေပါသည်။",
                    })
                    continue
                if len(name) > VILLAGE_NAME_MAX:
                    skipped.append({
                        "row": row_number,
                        "villageName": name,
                        "reason": (
                            f"ကျေးရွာအမည်သည် {VILLAGE_NAME_MAX} လုံးထက် "
                            "မကျော်ရပါ။"
                        ),
                    })
                    continue

                if _find_duplicate_village(
                    cursor, state_id, district_id, township_id, qv_id, name,
                ):
                    skipped.append({
                        "row": row_number,
                        "villageName": name,
                        "reason": "ကျေးရွာအုပ်စုအတွင်း ကျေးရွာစာရင်းတွင် ရှိပြီးဖြစ်ပါသည်။",
                    })
                    continue

                village_id = _next_village_id(
                    cursor, state_id, district_id, township_id, qv_id,
                )
                cursor.execute(
                    "INSERT INTO village "
                    "(stateID, districtID, townshipID, QVID, villageID, villageName) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (state_id, district_id, township_id, qv_id, village_id, name),
                )
                inserted += 1

            conn.commit()

            logger.info(
                "Temporary villages imported: %s/%s/%s/%s inserted=%d skipped=%d by %s",
                state_id, district_id, township_id, qv_id,
                inserted, len(skipped), user.get("loginName", "?"),
            )

            message = f"ကျေးရွာ {inserted} ခု ထည့်သွင်းပြီးပါပြီ။"
            if skipped:
                message += f" ကျေးရွာ {len(skipped)} ခုကို ကျော်လိုက်ပါသည်။"

            return {
                "success": True,
                "message": message,
                "inserted": inserted,
                "skipped": len(skipped),
                "errors": skipped,
                "district": district_id,
                "township": township_id,
                "qv": qv_id,
            }
        except HTTPException:
            raise
        except SQLAlchemyError:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.exception("Failed to import temporary villages from Excel")
            raise HTTPException(
                500, "Excel မှ ကျေးရွာများ ထည့်သွင်းရာတွင် အမှားဖြစ်ပေါ်ပါသည်။"
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    finally:
        try:
            wb.close()
        except Exception:
            pass
