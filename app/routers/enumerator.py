import logging
from fastapi import APIRouter, Request, Query, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.constants import EDITABLE_PERSON_FIELDS, EDITABLE_ANIMAL_FIELDS
from app.database import get_db_connection, get_db
from app.dependencies import (
    get_signed_in_user, _require_enumerator_web, _compat_session_state_id,
)
from app.lookups import (
    _get_all_states, _get_all_large_animals, _get_all_small_animals,
    load_animal_lookup, _get_all_breeding_animals,
)
from app.templating import templates
from app.utils import generate_formatted_id

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["enumerator"])


# ---------- Dashboard (enumerator) ----------
@router.get("/survey/dashboard", response_class=HTMLResponse)
async def survey_dashboard(request: Request, start_date: str = Query(""), end_date: str = Query("")):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=303)
    if str(user.get("role", "")).lower() != "enumerator":
        from app.config import ROLE_HOME
        return RedirectResponse(ROLE_HOME.get(user.get("role"), "/"), status_code=303)

    for key, label in (("stateID", "တိုင်းဒေသကြီး/ပြည်နယ်"),
                       ("districtID", "ခရိုင်"), ("townshipID", "မြို့နယ်")):
        if not user.get(key):
            raise HTTPException(403, f"Enumerator အကောင့်တွင် {label} မသတ်မှတ်ရသေးပါ။")

    user_id = user.get("id")
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT COUNT(*) AS c FROM personcv WHERE userId = %s", (user_id,))
        total_forms = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(DISTINCT QVID) AS c FROM personcv WHERE userId = %s", (user_id,))
        total_villages = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(DISTINCT householdNo) AS c FROM personcv WHERE userId = %s", (user_id,))
        total_households = int((cur.fetchone() or {}).get("c") or 0)
    finally:
        cur.close(); conn.close()

    household_stats = {"total": 0, "pending": 0, "collected": 0}
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""SELECT COUNT(*) AS total,
                              SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) AS pending,
                              SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) AS collected
                       FROM personcv WHERE userId = %s""", (user_id,))
        row = cur.fetchone() or {}
        household_stats = {
            "total":     int(row.get("total")     or 0),
            "pending":   int(row.get("pending")   or 0),
            "collected": int(row.get("collected") or 0),
        }
    finally:
        cur.close(); conn.close()

    return templates.TemplateResponse(request=request, name="formDashboard.html", context={
        "active_page": "home", "user": user,
        "total_forms": total_forms, "total_villages": total_villages,
        "total_households": total_households,
        "household_stats": household_stats,
        "filters": {"start_date": start_date, "end_date": end_date},
    })


# ---------- Part 1 GET (enumerator) ----------
@router.get("/enumerator/part1", response_class=HTMLResponse)
async def enumerator_web_part1(request: Request, db: Session = Depends(get_db)):
    user = _require_enumerator_web(request)
    request.session["stateID"] = str(user["stateID"])
    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey", "states": _get_all_states(),
        "user": user, "role": "enumerator",
        "form_id": "TEMP-FORM-ID-0001",
        "survey_prefix": "/enumerator",
    })


@router.get("/enumerator/locations")
async def enumerator_web_locations(request: Request):
    user = _require_enumerator_web(request)
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT districtID, districtName FROM district "
                    "WHERE stateID = %s AND districtID = %s",
                    (user["stateID"], user["districtID"]))
        district = cur.fetchone()
        cur.execute("SELECT townshipID, townshipName FROM township "
                    "WHERE stateID = %s AND districtID = %s AND townshipID = %s",
                    (user["stateID"], user["districtID"], user["townshipID"]))
        township = cur.fetchone()
        cur.execute("SELECT QVID, QVName FROM qv "
                    "WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName",
                    (user["stateID"], user["districtID"], user["townshipID"]))
        qvs = cur.fetchall()
        if not district or not township:
            raise HTTPException(403, "Enumerator အကောင့်၏ သတ်မှတ်ထားသော Location မမှန်ကန်ပါ။")
        return {"stateID": str(user["stateID"]), "district": district,
                "township": township, "qvs": qvs}
    finally:
        cur.close(); conn.close()


# ---------- Lookups ----------
@router.get("/enumerator/api/lookups")
async def get_animal_lookups(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        return {"status": "success", "lookup": load_animal_lookup(cur)}
    except Exception:
        logger.exception("Failed to load animal lookup data")
        raise HTTPException(500, "Lookup data မရပါ။")
    finally:
        cur.close(); conn.close()


# ---------- Edit-form page + APIs ----------
@router.get("/enumerator/edit-form", response_class=HTMLResponse)
async def edit_form_page(request: Request):
    user = get_signed_in_user(request)
    if user.get("role") != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    return templates.TemplateResponse(request=request, name="edit_form.html", context={
        "request": request, "user": user,
        "role": user.get("role", ""), "active_page": "edit_form",
    })


@router.get("/enumerator/api/forms/{formID}")
async def get_form_for_edit(formID: str, request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT p.*, s.stateName, d.districtName, t.townshipName, q.QVName
            FROM personcv p
            LEFT JOIN state    s ON s.stateID = p.stateID
            LEFT JOIN district d ON d.stateID = p.stateID AND d.districtID = p.districtID
            LEFT JOIN township t ON t.stateID = p.stateID AND t.districtID = p.districtID
                                AND t.townshipID = p.townshipID
            LEFT JOIN qv       q ON q.stateID = p.stateID AND q.districtID = p.districtID
                                AND q.townshipID = p.townshipID AND q.QVID = p.QVID
            WHERE p.formID = %s AND p.userId = %s LIMIT 1
        """, (formID, user_id))
        person = cur.fetchone()
        if not person:
            raise HTTPException(404, "Form မတွေ့ပါ သို့မဟုတ် မိမိပိုင်ဒေတာ မဟုတ်ပါ။")
        cur.execute("""SELECT animalTypeID, animalID, speciesID, ageID, genderID, dataCount
                       FROM collecteddata WHERE formID = %s""", (formID,))
        collected = cur.fetchall()
        return {
            "formID": formID,
            "personcv": person,
            "collecteddata": collected,
            "lookup": load_animal_lookup(cur),
        }
    finally:
        cur.close(); conn.close()


@router.put("/enumerator/api/forms/{formID}")
async def update_existing_form(formID: str, request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Request JSON မမှန်ကန်ပါ။")
    person_data  = payload.get("personcv") or {}
    animal_data  = payload.get("collecteddata") or []

    person_values = {k: v for k, v in person_data.items() if k in EDITABLE_PERSON_FIELDS}
    for key in ("age", "headAge"):
        if key in person_values and str(person_values[key]).strip() != "":
            try:
                person_values[key] = int(person_values[key])
            except (TypeError, ValueError):
                raise HTTPException(422, f"{key} သည် ကိန်းဂဏန်း ဖြစ်ရပါမည်။")

    cleaned_animals = []
    for row in animal_data:
        clean = {k: row.get(k) for k in EDITABLE_ANIMAL_FIELDS}
        if not any(str(v or "").strip() for v in clean.values()):
            continue
        try:
            count_int = int(str(clean.get("dataCount") or "0").strip())
            if count_int < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(422, "အရေအတွက် မမှန်ပါ။")
        clean["dataCount"] = str(count_int)
        cleaned_animals.append(clean)

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("""SELECT formID FROM personcv
                       WHERE formID = %s AND userId = %s LIMIT 1 FOR UPDATE""",
                    (formID, user_id))
        if not cur.fetchone():
            conn.rollback()
            raise HTTPException(404, "သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။")

        if person_values:
            assignments = ", ".join(f"`{k}` = %s" for k in person_values)
            cur.execute(f"UPDATE personcv SET {assignments} WHERE formID = %s AND userId = %s",
                        tuple(list(person_values.values()) + [formID, user_id]))

        cur.execute("DELETE FROM collecteddata WHERE formID = %s", (formID,))
        for row in cleaned_animals:
            cur.execute(
                "INSERT INTO collecteddata (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (formID, row.get("animalTypeID"), row.get("animalID"),
                 row.get("speciesID"), row.get("ageID"), row.get("genderID"),
                 row.get("dataCount", "0")),
            )
        conn.commit()
        return {"status": "success", "message": "သိမ်းဆည်းပြီးပါပြီ။",
                "formID": formID, "animalRecordsSaved": len(cleaned_animals)}
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        logger.exception("Existing survey update failed")
        raise HTTPException(500, "ဒေတာ Update မအောင်မြင်ပါ။")
    finally:
        cur.close(); conn.close()


@router.delete("/enumerator/api/forms/{formID}")
async def delete_existing_form(formID: str, request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("""SELECT formID FROM personcv
                       WHERE formID = %s AND userId = %s LIMIT 1 FOR UPDATE""",
                    (formID, user_id))
        if not cur.fetchone():
            conn.rollback()
            raise HTTPException(404, "သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။")
        cur.execute("DELETE FROM collecteddata WHERE formID = %s", (formID,))
        deleted_animals = cur.rowcount
        cur.execute("DELETE FROM personcv WHERE formID = %s AND userId = %s",
                    (formID, user_id))
        deleted_person = cur.rowcount
        conn.commit()
        return {"status": "success", "message": "ဒေတာကို ဖျက်ပြီးပါပြီ။",
                "formID": formID, "deletedAnimals": deleted_animals,
                "deletedPerson": deleted_person}
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        logger.exception("Delete form failed")
        raise HTTPException(500, "ဒေတာဖျက်ခြင်း မအောင်မြင်ပါ။")
    finally:
        cur.close(); conn.close()


# ---------- My forms + filters ----------
@router.get("/enumerator/api/my-forms")
async def get_my_forms(
    request: Request,
    qv: str = Query(""), interviewer: str = Query(""),
    head_name: str = Query(""), household_no: str = Query(""),
    form_id: str = Query(""), date_from: str = Query(""),
    date_to: str = Query(""), collection_status: str = Query(""),
):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    if collection_status not in ("", "0", "1"):
        raise HTTPException(422, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")

    user_id = user["id"]
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT p.formID, p.name, p.householdNo, p.interviewDate, p.WardName,
                   q.QVName, p.Interviewer, p.headName, p.status
            FROM personcv p
            LEFT JOIN qv q ON q.QVID = p.QVID AND q.stateID = p.stateID
                         AND q.districtID = p.districtID AND q.townshipID = p.townshipID
            WHERE p.userId = %s
        """
        params = [user_id]
        if collection_status != "":
            sql += " AND p.status = %s"; params.append(int(collection_status))
        if qv.strip():
            sql += " AND p.QVID = %s"; params.append(qv.strip())
        if interviewer.strip():
            sql += " AND p.Interviewer LIKE %s"; params.append(f"%{interviewer.strip()}%")
        if head_name.strip():
            sql += " AND p.headName LIKE %s"; params.append(f"%{head_name.strip()}%")
        if household_no.strip():
            sql += " AND p.householdNo LIKE %s"; params.append(f"%{household_no.strip()}%")
        if form_id.strip():
            sql += " AND p.formID LIKE %s"; params.append(f"%{form_id.strip()}%")
        if date_from.strip():
            sql += " AND p.interviewDate >= %s"; params.append(date_from.strip())
        if date_to.strip():
            sql += " AND p.interviewDate <= %s"; params.append(date_to.strip())
        sql += " ORDER BY p.interviewDate DESC, p.formID DESC"
        cur.execute(sql, tuple(params))
        return {"status": "success", "forms": cur.fetchall()}
    except SQLAlchemyError:
        logger.exception("Failed to load enumerator forms")
        raise HTTPException(503, "ဒေတာ ရယူမရပါ။")
    finally:
        cur.close(); conn.close()


@router.get("/enumerator/api/my-forms-filters")
async def get_my_forms_filters(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""SELECT DISTINCT p.QVID, q.QVName FROM personcv p
                       LEFT JOIN qv q ON q.QVID = p.QVID AND q.stateID = p.stateID
                                    AND q.districtID = p.districtID AND q.townshipID = p.townshipID
                       WHERE p.userId = %s AND p.QVID IS NOT NULL AND p.QVID != ''""",
                    (user_id,))
        qvs = cur.fetchall()
        cur.execute("SELECT DISTINCT Interviewer FROM personcv "
                    "WHERE userId = %s AND Interviewer IS NOT NULL AND Interviewer != ''",
                    (user_id,))
        interviewers = [r["Interviewer"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT headName FROM personcv "
                    "WHERE userId = %s AND headName IS NOT NULL AND headName != ''",
                    (user_id,))
        headNames = [r["headName"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT householdNo FROM personcv "
                    "WHERE userId = %s AND householdNo IS NOT NULL AND householdNo != ''",
                    (user_id,))
        householdNos = [r["householdNo"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT formID FROM personcv "
                    "WHERE userId = %s AND formID IS NOT NULL AND formID != ''",
                    (user_id,))
        formIDs = [r["formID"] for r in cur.fetchall()]
        return {"status": "success", "qvs": qvs, "interviewers": interviewers,
                "headNames": headNames, "householdNos": householdNos, "formIDs": formIDs}
    finally:
        cur.close(); conn.close()


# ---------- Household registration ----------
@router.get("/enumerator/household-register", response_class=HTMLResponse)
async def household_register(request: Request):
    _require_enumerator_web(request)
    return RedirectResponse("/enumerator/part1", status_code=303)


@router.post("/api/enumerator/households")
async def create_household(request: Request):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body.")

    qv_id        = str(payload.get("QVID") or "").strip()
    ward_name    = str(payload.get("WardName") or "").strip()
    household_no = str(payload.get("householdNo") or "").strip()
    collection_status = str(payload.get("collectionStatus") or "pending").strip().lower()
    remarks = str(payload.get("remarks") or "").strip() or None

    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု ရွေးချယ်ပါ။")
    if not ward_name:
        raise HTTPException(400, "ရပ်ကွက်အမည် ဖြည့်ပါ။")
    if not household_no:
        raise HTTPException(400, "အိမ်ထောင်စုအမှတ် ဖြည့်ပါ။")
    if collection_status not in ("pending", "cannot_collect"):
        raise HTTPException(400, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")
    if collection_status == "cannot_collect" and not remarks:
        raise HTTPException(400, "ကောက်ယူလို့မရနိုင်သည့် အကြောင်းပြချက် ဖြည့်ပါ။")
    if collection_status == "pending":
        remarks = None

    user_id     = user["id"]
    state_id    = user.get("stateID")
    district_id = user.get("districtID")
    township_id = user.get("townshipID")
    if not all([state_id, district_id, township_id]):
        raise HTTPException(400, "Enumerator ၏ တည်နေရာ မပြည့်စုံပါ။")

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cur.execute("SELECT 1 FROM qv WHERE QVID = %s AND stateID = %s "
                    "AND districtID = %s AND townshipID = %s LIMIT 1",
                    (qv_id, state_id, district_id, township_id))
        if not cur.fetchone():
            conn.rollback()
            raise HTTPException(403, "သတ်မှတ်ထားသော မြို့နယ်အတွင်းရှိ ကျေးရွာအုပ်စု ကို ရွေးပါ။")
        cur.execute("""SELECT householdID FROM householdRegister
                       WHERE stateID=%s AND districtID=%s AND townshipID=%s
                         AND QVID=%s AND WardName=%s AND householdNo=%s LIMIT 1""",
                    (state_id, district_id, township_id, qv_id, ward_name, household_no))
        if cur.fetchone():
            conn.rollback()
            raise HTTPException(409, "ဤအိမ်ထောင်စု ရှိပြီးသားဖြစ်ပါသည်။")
        cur.execute("""INSERT INTO householdRegister
                       (stateID, districtID, townshipID, QVID, WardName,
                        householdNo, collectionStatus, remarks, createdBy)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (state_id, district_id, township_id, qv_id, ward_name,
                     household_no, collection_status, remarks, user_id))
        new_id = cur.lastrowid
        conn.commit()
        return {"status": "success",
                "message": ("အိမ်ထောင်စုစာရင်း (ကောက်ယူလို့မရနိုင်) သိမ်းဆည်းပြီးပါပြီ။"
                            if collection_status == "cannot_collect"
                            else "အိမ်ထောင်စုစာရင်း သိမ်းဆည်းပြီးပါပြီ။"),
                "householdID": new_id, "collectionStatus": collection_status}
    except HTTPException:
        raise
    except IntegrityError:
        conn.rollback()
        raise HTTPException(409, "ဤအိမ်ထောင်စု ရှိပြီးသားဖြစ်ပါသည်။")
    except Exception:
        conn.rollback()
        logger.exception("household create failed")
        raise HTTPException(500, "ဒေတာသိမ်းဆည်းမှု မအောင်မြင်ပါ။")
    finally:
        cur.close(); conn.close()