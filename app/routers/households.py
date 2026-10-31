import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.constants import AGE_TO_KEY
from app.database import get_db_connection
from app.dependencies import get_signed_in_user
from app.lookups import _get_user_state_name
from app.templating import templates
from app.utils import _resolve_date_range

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["households"])


def _query_household_records(cursor, role, user, state="", district="",
                             township="", qv="", search="", form_id="",
                             household_no="", head_name="", limit=None,
                             offset=0, start_date="", end_date=""):
    conds = ["1=1"]
    params = []

    if role == "state":
        conds.append("pc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["pc.stateID = %s", "pc.districtID = %s"])
        params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["pc.stateID = %s", "pc.districtID = %s", "pc.townshipID = %s"])
        params.extend([user["stateID"], user["districtID"], user["townshipID"]])

    if role in ("admin", "union") and state and state.strip():
        conds.append("pc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("pc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("pc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("pc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(pc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    if search and search.strip():
        like = f"%{search.strip()}%"
        conds.append("(pc.name LIKE %s OR pc.householdNo LIKE %s OR pc.headName LIKE %s OR pc.formID LIKE %s)")
        params.extend([like, like, like, like])

    if form_id and form_id.strip():
        conds.append("pc.formID LIKE %s"); params.append(f"%{form_id.strip()}%")
    if household_no and household_no.strip():
        conds.append("pc.householdNo LIKE %s"); params.append(f"%{household_no.strip()}%")
    if head_name and head_name.strip():
        conds.append("pc.headName LIKE %s"); params.append(f"%{head_name.strip()}%")

    where = " AND ".join(conds)

    sql = f"""
        SELECT
            pc.formID, pc.householdNo, pc.name AS respondent_name,
            pc.gender AS respondent_gender, pc.age AS respondent_age,
            pc.eduStatus AS respondent_edu, pc.phoneNo AS respondent_phone,
            pc.interviewDate, pc.headName, pc.headGender, pc.headAge,
            pc.headEduStatus, pc.headPhoneNo, pc.Interviewer,
            pc.interviewerPhoneNo, pc.WardName, pc.stateID, pc.districtID,
            pc.townshipID, pc.QVID,
            st.stateName AS state_name,
            dt.districtName AS district_name,
            ts.townshipName AS township_name,
            qv.QVName AS qv_name,
            COALESCE(ct.large_total, 0) AS large_total,
            COALESCE(ct.small_total, 0) AS small_total,
            COALESCE(ct.poultry_total, 0) AS poultry_total,
            COALESCE(ct.breeding_total, 0) AS breeding_total
        FROM personcv AS pc
        LEFT JOIN state    AS st ON st.stateID = pc.stateID
        LEFT JOIN district AS dt ON dt.stateID = pc.stateID AND dt.districtID = pc.districtID
        LEFT JOIN township AS ts ON ts.stateID = pc.stateID
                                 AND ts.districtID = pc.districtID
                                 AND ts.townshipID = pc.townshipID
        LEFT JOIN qv       ON qv.stateID = pc.stateID
                          AND qv.districtID = pc.districtID
                          AND qv.townshipID = pc.townshipID
                          AND qv.QVID = pc.QVID
        LEFT JOIN (
            SELECT formID,
                SUM(CASE WHEN animalTypeID = 'atID01' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS large_total,
                SUM(CASE WHEN animalTypeID = 'atID02' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS small_total,
                SUM(CASE WHEN animalTypeID = 'atID03' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS poultry_total,
                SUM(CASE WHEN animalTypeID = 'atID04' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS breeding_total
            FROM collecteddata GROUP BY formID
        ) AS ct ON ct.formID = pc.formID
        WHERE {where}
        ORDER BY pc.interviewDate DESC, pc.formID DESC
    """
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])

    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def _query_household_detail(cursor, form_id):
    sql = """
        SELECT
            cd.animalTypeID, cd.animalID, cd.speciesID, cd.ageID, cd.genderID,
            CAST(cd.dataCount AS UNSIGNED) AS data_count,
            COALESCE(la.animalName, ya.animalName, lv.animalName, bs.animalName, cd.animalID) AS animal_name,
            COALESCE(ls.speciesName, ys.speciesName, lss.speciesName, cd.speciesID) AS species_name,
            COALESCE(atg.ageName, a.ageName, cd.ageID) AS age_name,
            COALESCE(g.genderName, cd.genderID) AS gender_name
        FROM collecteddata AS cd
        LEFT JOIN largeanimals     AS la  ON cd.animalTypeID = 'atID01' AND la.animalID = cd.animalID
        LEFT JOIN largespecies     AS ls  ON cd.animalTypeID = 'atID01' AND ls.speciesID = cd.speciesID AND ls.animalID = cd.animalID
        LEFT JOIN younganimals     AS ya  ON cd.animalTypeID = 'atID02' AND ya.animalID = cd.animalID
        LEFT JOIN youngspecies     AS ys  ON cd.animalTypeID = 'atID02' AND ys.speciesID = cd.speciesID AND ys.animalID = cd.animalID
        LEFT JOIN livestock        AS lv  ON cd.animalTypeID = 'atID03' AND lv.animalID = cd.animalID
        LEFT JOIN livestockspecies AS lss ON cd.animalTypeID = 'atID03' AND lss.speciesID = cd.speciesID AND lss.animalID = cd.animalID
        LEFT JOIN breedingstock    AS bs  ON cd.animalTypeID = 'atID04' AND bs.animalID = cd.animalID
        LEFT JOIN age              AS a   ON a.ageID = cd.ageID
        LEFT JOIN agetype          AS atg ON atg.ageID = cd.ageID
            AND atg.animalTypeID = cd.animalTypeID
            AND (atg.animalID IS NULL OR atg.animalID = '' OR atg.animalID = cd.animalID)
        LEFT JOIN gender           AS g   ON g.genderID = cd.genderID
        WHERE cd.formID = %s
        ORDER BY cd.animalTypeID, cd.animalID, cd.ageID, cd.genderID
    """
    cursor.execute(sql, (form_id,))
    return cursor.fetchall()


def _build_household_record(row, detail_rows):
    def _n(v):
        try: return int(v or 0)
        except (TypeError, ValueError): return 0

    POULTRY_AGE_KEY = {
        "ageID07": "young", "ageID08": "medium", "ageID09": "adult",
        "ageID10": "young", "ageID11": "adult",
        "ageID12": "young", "ageID13": "medium", "ageID14": "adult",
        "ageID15": "young", "ageID16": "medium",
    }
    GENDER_KEYS_BY_TYPE = {
        "atID01": {"g01": "male", "g02": "castrated", "g03": "female"},
        "atID02": {"g01": "male", "g02": "castrated", "g03": "female"},
        "atID03": {"g01": "male", "g03": "female"},
        "atID04": {"g01": "male", "g03": "female"},
    }

    large, small, poultry = [], [], []
    breeding = {}

    for d in detail_rows:
        atid = (d.get("animalTypeID") or "").strip()
        aid  = (d.get("animalID") or "").strip()
        age  = (d.get("ageID") or "").strip()
        gid  = (d.get("genderID") or "").strip()
        cnt  = _n(d.get("data_count"))
        age_name_val = d.get("age_name") or ""

        if atid == "atID01":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in large if x["animalID"] == aid
                         and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id,
                        "species": d.get("animal_name") or aid,
                        "breed": d.get("species_name") or "",
                        "total": 0, "age_name": age_name_val}
                large.append(row_)
            ak = AGE_TO_KEY.get(atid, {}).get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID02":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in small if x["animalID"] == aid
                         and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id,
                        "species": d.get("animal_name") or aid,
                        "breed": d.get("species_name") or "",
                        "total": 0, "age_name": age_name_val}
                small.append(row_)
            ak = AGE_TO_KEY["atID02"].get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID03":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in poultry if x["animalID"] == aid
                         and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id,
                        "species": d.get("animal_name") or aid,
                        "breed": d.get("species_name") or "",
                        "total": 0, "age_name": age_name_val}
                poultry.append(row_)
            ak = POULTRY_AGE_KEY.get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID04":
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if gk in ("male", "female"):
                if aid not in breeding:
                    breeding[aid] = {"animalID": aid, "male": 0, "female": 0,
                                     "species": d.get("animal_name") or aid,
                                     "age_name": age_name_val}
                breeding[aid][gk] += cnt

    return {
        "id": row.get("formID") or "",
        "householdNo": row.get("householdNo") or "",
        "state": row.get("state_name") or "",
        "district": row.get("district_name") or "",
        "township": row.get("township_name") or "",
        "village_tract": row.get("qv_name") or "",
        "ward_village": row.get("WardName") or "",
        "interview_date": str(row.get("interviewDate") or ""),
        "respondent": {
            "name": row.get("respondent_name") or "",
            "gender": row.get("respondent_gender") or "",
            "age": row.get("respondent_age") or "",
            "education": row.get("respondent_edu") or "",
            "phone": row.get("respondent_phone") or "",
        },
        "household_head": {
            "name": row.get("headName") or "",
            "gender": row.get("headGender") or "",
            "age": row.get("headAge") or "",
            "education": row.get("headEduStatus") or "",
            "phone": row.get("headPhoneNo") or "",
        },
        "has_raised_animals": "yes" if (large or small) else "no",
        "large_animals": large,
        "small_animals": small,
        "has_poultry": "yes" if poultry else "no",
        "poultry": poultry,
        "breeding": breeding,
        "interviewer": {
            "name": row.get("Interviewer") or "",
            "phone": row.get("interviewerPhoneNo") or "",
        },
        "large_total": _n(row.get("large_total")),
        "small_total": _n(row.get("small_total")),
        "poultry_total": _n(row.get("poultry_total")),
        "breeding_total": _n(row.get("breeding_total")),
    }


# ============================================================
# ROUTES
# ============================================================
@router.get("/admin/records", response_class=HTMLResponse)
async def admin_records(
    request: Request,
    state: str = Query(""), district: str = Query(""),
    township: str = Query(""), qv: str = Query(""),
    search: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"):
        raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    records = []
    district_name_for_js = ""
    township_name_for_js = ""
    try:
        if role == "district" and user.get("districtID"):
            cur.execute("SELECT districtName FROM district "
                        "WHERE stateID = %s AND districtID = %s",
                        (user.get("stateID"), user.get("districtID")))
            d_row = cur.fetchone()
            district_name_for_js = d_row["districtName"] if d_row else ""
        elif role == "township" and user.get("townshipID"):
            cur.execute("SELECT townshipName FROM township "
                        "WHERE stateID = %s AND districtID = %s AND townshipID = %s",
                        (user.get("stateID"), user.get("districtID"),
                         user.get("townshipID")))
            t_row = cur.fetchone()
            township_name_for_js = t_row["townshipName"] if t_row else ""
            cur.execute("SELECT districtName FROM district "
                        "WHERE stateID = %s AND districtID = %s",
                        (user.get("stateID"), user.get("districtID")))
            d_row = cur.fetchone()
            district_name_for_js = d_row["districtName"] if d_row else ""

        rows = _query_household_records(
            cur, role, user, state, district, township, qv, search,
            start_date=start_date, end_date=end_date,
        )
        for r in rows:
            detail = _query_household_detail(cur, r["formID"])
            records.append(_build_household_record(r, detail))
    except SQLAlchemyError as e:
        logger.error("admin_records DB error: %s", e)
    finally:
        cur.close(); conn.close()

    return templates.TemplateResponse(request=request, name="reportFormData.html", context={
        "active_page": "records", "role": role, "records": records,
        "user_state_id": user.get("stateID") or "",
        "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "",
        "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "",
        "user_township_name": township_name_for_js,
        "filters": {"state": state, "district": district, "township": township,
                    "qv": qv, "search": search,
                    "start_date": start_date, "end_date": end_date},
    })


@router.get("/api/admin/filter-options")
async def admin_filter_options(
    request: Request,
    state: str = Query(""), district: str = Query(""),
    township: str = Query(""), qv: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ရန်လိုအပ်ပါသည်။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"):
        raise HTTPException(403, "ခွင့်မရှိပါ။")

    if role == "state":
        state = user.get("stateID") or ""
    elif role == "district":
        state = user.get("stateID") or ""
        district = user.get("districtID") or ""
    elif role == "township":
        state = user.get("stateID") or ""
        district = user.get("districtID") or ""
        township = user.get("townshipID") or ""

    if not qv:
        return {"formIDs": [], "householdNos": [], "headNames": []}

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        where = ["QVID = %s"]; args = [qv]
        if state:    where.append("stateID = %s");    args.append(state)
        if district: where.append("districtID = %s"); args.append(district)
        if township: where.append("townshipID = %s"); args.append(township)
        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            where.append("DATE(interviewDate) BETWEEN %s AND %s")
            args.extend([s, e])
        where_sql = " AND ".join(where)

        cur.execute(f"SELECT DISTINCT formID AS value FROM personcv WHERE {where_sql} "
                    "AND formID IS NOT NULL AND formID <> '' ORDER BY formID", tuple(args))
        form_rows = cur.fetchall()
        cur.execute(f"SELECT DISTINCT householdNo AS value FROM personcv WHERE {where_sql} "
                    "AND householdNo IS NOT NULL AND householdNo <> '' ORDER BY householdNo",
                    tuple(args))
        household_rows = cur.fetchall()
        cur.execute(f"SELECT DISTINCT headName AS value FROM personcv WHERE {where_sql} "
                    "AND headName IS NOT NULL AND headName <> '' ORDER BY headName",
                    tuple(args))
        head_rows = cur.fetchall()

        return {
            "formIDs": [{"value": r["value"], "label": r["value"]} for r in form_rows],
            "householdNos": [{"value": r["value"], "label": r["value"]} for r in household_rows],
            "headNames": [{"value": r["value"], "label": r["value"]} for r in head_rows],
        }
    except Exception:
        logger.exception("admin_filter_options database error")
        raise HTTPException(500, "Dropdown data ရယူရာတွင် Database error ဖြစ်နေပါသည်။")
    finally:
        cur.close(); conn.close()


@router.get("/api/admin/records")
async def api_admin_records(
    request: Request,
    state: str = Query(""), district: str = Query(""),
    township: str = Query(""), qv: str = Query(""), search: str = Query(""),
    formID: str = Query(""), householdNo: str = Query(""),
    headName: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"):
        raise HTTPException(403, "ကြည့်ခွင့်မရှိပါ။")

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        rows = _query_household_records(
            cur, role, user, state=state, district=district, township=township,
            qv=qv, search=search, form_id=formID, household_no=householdNo,
            head_name=headName, start_date=start_date, end_date=end_date,
        )
        records = []
        for r in rows:
            detail = _query_household_detail(cur, r["formID"])
            records.append(_build_household_record(r, detail))
        return {"status": "success", "records": records, "count": len(records)}
    except SQLAlchemyError:
        logger.exception("api_admin_records DB error")
        raise HTTPException(500, "Database error ဖြစ်နေပါသည်။")
    finally:
        cur.close(); conn.close()

# ============================================================
# 🏘️ ADMIN HOUSEHOLD SUMMARY
# ============================================================
@router.get("/admin/households", response_class=HTMLResponse)
async def admin_households(request: Request):
    user = get_signed_in_user(request)
    role = str(user.get("role", "")).lower()
    if role not in ("admin", "union", "state", "district", "township"):
        raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    scope_fields = {
        "admin": (),
        "union": (),
        "state": ("stateID",),
        "district": ("stateID", "districtID"),
        "township": ("stateID", "districtID", "townshipID"),
    }[role]

    if any(not user.get(field) for field in scope_fields):
        raise HTTPException(403, "သင့်အကောင့်၏ သတ်မှတ်နယ်မြေ မပြည့်စုံပါ။")

    scope_sql = "".join(f" AND pc.{field} = %s" for field in scope_fields)
    scope_params = tuple(user[field] for field in scope_fields)

    collected = []
    not_collected = []
    error = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"""
            SELECT pc.formID, pc.householdNo, pc.headName, pc.name,
                   pc.interviewDate, pc.status,
                   COALESCE(ts.townshipName, pc.townshipID) AS township_name,
                   COALESCE(q.QVName, pc.QVID) AS qv_name,
                   COALESCE(animals.total, 0) AS animal_total
            FROM personcv pc
            LEFT JOIN township ts ON ts.stateID = pc.stateID
                AND ts.districtID = pc.districtID AND ts.townshipID = pc.townshipID
            LEFT JOIN qv q ON q.stateID = pc.stateID AND q.districtID = pc.districtID
                AND q.townshipID = pc.townshipID AND q.QVID = pc.QVID
            LEFT JOIN (
                SELECT formID, SUM(CAST(dataCount AS UNSIGNED)) AS total
                FROM collecteddata GROUP BY formID
            ) animals ON animals.formID = pc.formID
            WHERE pc.status IN (0, 1){scope_sql}
            ORDER BY pc.interviewDate DESC, pc.formID DESC
        """, scope_params)
        for row in cursor.fetchall():
            (collected if int(row["status"]) == 1 else not_collected).append(row)
    except SQLAlchemyError:
        logger.exception("Failed to load admin household summary")
        error = "အိမ်ထောင်စုစာရင်း ရယူမရပါ။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return templates.TemplateResponse(
        request=request,
        name="adminHouseholds.html",
        status_code=503 if error else 200,
        context={
            "user": user,
            "role": role,
            "active_page": "household_summary",
            "collected": collected,
            "not_collected": not_collected,
            "error": error,
        },
    )