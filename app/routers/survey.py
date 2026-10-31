import json  
import logging
from datetime import datetime
from typing import Annotated, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
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

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["survey"])


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
    db: Session = Depends(get_db),
):
    logger.info("formID from part1 %s", formID)
    enumerator_user = _guard_enumerator_web_route(request)

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
async def compat_submit_survey(formID: str, request: Request, db: Session = Depends(get_db)):
    enumerator_user = _guard_enumerator_web_route(request)
    state_id = str(enumerator_user["stateID"]) if enumerator_user else _compat_session_state_id(request)

    step1 = request.session.get("step1") or {}
    session_user = request.session.get("user") or {}
    user_id = session_user.get("id")
    if user_id is None:
        raise HTTPException(400, "User session မတွေ့ပါ။ ပြန် Login လုပ်ပါ။")

    if enumerator_user:
        if (str(step1.get("districtID")) != str(enumerator_user["districtID"])
                or str(step1.get("townshipID")) != str(enumerator_user["townshipID"])):
            raise HTTPException(403, "Survey Location သည် Enumerator ၏ သတ်မှတ်ဧရိယာနှင့် မကိုက်ညီပါ။")

    if not state_id or not step1:
        raise HTTPException(400, "Survey အချက်အလက် မပြည့်စုံပါ။")

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

    current_year = datetime.now().year
    try:
        row = db.execute(
            text("""SELECT COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) + 1 AS next_num
                    FROM personcv WHERE formID LIKE :pattern"""),
            {"pattern": f"FORM-{current_year}-%"},
        ).fetchone()
        next_num = int(row[0]) if row and row[0] else 1
    except Exception as e:
        logger.error("Form ID generation failed: %s", e)
        raise HTTPException(500, "Form ID ဖန်တီးမှု မအောင်မြင်ပါ။")

    new_form_id = generate_formatted_id(next_num)
    logger.info("tempID=%s, generated FormID=%s (MAX-based)", formID, new_form_id)
    formID = new_form_id

    conn = get_db_connection(); cur = conn.cursor()
    try:
        conn.start_transaction()

        cur.execute("SELECT userId FROM personcv WHERE formID = %s FOR UPDATE", (formID,))
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
                    interviewerPhoneNo = %s, status = %s
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
                    headAge, Interviewer, interviewerPhoneNo, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                formID, user_id, state_id, step1.get("districtID"),
                step1.get("townshipID"), step1.get("qvID"), step1.get("wardName"),
                step1.get("houseHoldNo"), step1.get("interviewDate"), step1.get("name"),
                step1.get("gender"), step1.get("eduStatus"), step1.get("phoneNo"),
                int(step1.get("age") or 0), step1.get("headName"),
                step1.get("headEduStatus"), step1.get("headGender"),
                step1.get("headPhoneNo"), step1.get("headAge"),
                interviewer, interviewer_phone, int(collecting),
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

        for key in ("stateID", "formID", "step1", "animals_data", "livestock_data",
                    "breeding_animals_data", "interviewer", "interviewerPhoneNo"):
            request.session.pop(key, None)

        return {
            "status": "success",
            "message": "Survey saved successfully",
            "formID": formID,
            "animalRecordsSaved": len(all_animals),
            "collectionStatus": int(collecting),
            "userId": user_id,
        }

    except HTTPException:
        conn.rollback(); raise
    except Exception:
        conn.rollback()
        logger.exception("Survey submit failed for formID=%s userId=%s", formID, user_id)
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