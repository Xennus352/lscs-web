import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


from app.database import SessionLocal
from app.lookups import _get_user_state_name
from app.templating import templates
from app.utils import _resolve_date_range

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["dashboard"])


# ============================================================
# 📊 MAIN DASHBOARD QUERY (shared by / and /admin)
# ============================================================
def query_dashboard_data(user, state=None, district=None, township=None,
                         qv=None, start_date=None, end_date=None):
    role = user["role"]
    db = SessionLocal()
    region_name = ""
    animals = []
    stats = {"large": 0, "small": 0, "poultry": 0, "breeding": 0, "total": 0}

    try:
        try:
            if role == "union":
                region_name = "တစ်နိုင်ငံလုံး"
            elif role == "state":
                r = db.execute(text("SELECT stateName AS name FROM state WHERE stateID = :sid"),
                               {"sid": user["stateID"]}).fetchone()
                region_name = r[0] if r else (user.get("stateID") or "")
            elif role == "district":
                r = db.execute(
                    text("SELECT districtName AS name FROM district "
                         "WHERE stateID = :sid AND districtID = :did"),
                    {"sid": user["stateID"], "did": user["districtID"]},
                ).fetchone()
                region_name = r[0] if r else (user.get("districtID") or "")
            elif role in ("township", "enumerator"):
                r = db.execute(
                    text("SELECT townshipName AS name FROM township "
                         "WHERE stateID = :sid AND districtID = :did AND townshipID = :tid"),
                    {"sid": user["stateID"], "did": user["districtID"], "tid": user["townshipID"]},
                ).fetchone()
                region_name = r[0] if r else (user.get("townshipID") or "")
        except SQLAlchemyError as e:
            logger.warning("Region lookup error: %s", e)

        q_conds = ["cd.animalTypeID IN ('atID01', 'atID02', 'atID03', 'atID04')"]
        q_params = {}

        if role == "union":
            if state and state.strip():
                q_conds.append("loc.stateID = :sid"); q_params["sid"] = state.strip()
            if district and district.strip():
                q_conds.append("loc.districtID = :did"); q_params["did"] = district.strip()
            if township and township.strip():
                q_conds.append("loc.townshipID = :tid"); q_params["tid"] = township.strip()
        elif role == "state":
            q_conds.append("loc.stateID = :sid"); q_params["sid"] = user["stateID"]
        elif role == "district":
            q_conds.extend(["loc.stateID = :sid", "loc.districtID = :did"])
            q_params["sid"] = user["stateID"]; q_params["did"] = user["districtID"]
        elif role in ("township", "enumerator"):
            q_conds.extend(["loc.stateID = :sid", "loc.districtID = :did", "loc.townshipID = :tid"])
            q_params["sid"] = user["stateID"]
            q_params["did"] = user["districtID"]
            q_params["tid"] = user["townshipID"]

        if role in ("admin", "union") and state and state.strip():
            q_conds.append("loc.stateID = :sid"); q_params["sid"] = state.strip()
        if role in ("admin", "union", "state") and district and district.strip():
            q_conds.append("loc.districtID = :did"); q_params["did"] = district.strip()
        if role in ("admin", "union", "state", "district") and township and township.strip():
            q_conds.append("loc.townshipID = :tid"); q_params["tid"] = township.strip()
        if qv and qv.strip():
            q_conds.append("loc.QVID = :qvid"); q_params["qvid"] = qv.strip()

        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            q_conds.append("DATE(loc.interviewDate) BETWEEN :start_date AND :end_date")
            q_params["start_date"] = s; q_params["end_date"] = e

        where = " AND ".join(q_conds)

        sql = text(f"""
            SELECT
                COALESCE(at.animalName, cd.animalTypeID) AS animal_type,
                cd.animalTypeID AS animal_type_id,
                cd.animalID    AS animal_id,
                CASE
                    WHEN cd.animalTypeID = 'atID01' THEN COALESCE(la.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID02' THEN COALESCE(ya.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID03' THEN COALESCE(lv.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID04' THEN COALESCE(bst.animalName, cd.animalID)
                    ELSE cd.animalID
                END AS animal_name,
                CASE
                    WHEN cd.animalTypeID = 'atID04' THEN 'မျိုးတိရစ္ဆာန်'
                    WHEN cd.animalTypeID = 'atID03' THEN COALESCE(lss.speciesName, cd.speciesID)
                    ELSE COALESCE(ls.speciesName, ys.speciesName, cd.speciesID)
                END AS species_name,
                COALESCE(atg.ageName, a.ageName, cd.ageID) AS age_name,
                COALESCE(g.genderName, cd.genderID) AS gender_name,
                SUM(cd.dataCount) AS total_count
            FROM collecteddata AS cd
            JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate
                  FROM personcv) AS loc ON loc.formID = cd.formID
            LEFT JOIN animaltype AS at ON at.animalTypeID = cd.animalTypeID
            LEFT JOIN largeanimals AS la ON cd.animalTypeID = 'atID01' AND la.animalID = cd.animalID
            LEFT JOIN largespecies AS ls ON cd.animalTypeID = 'atID01' AND ls.speciesID = cd.speciesID AND ls.animalID = cd.animalID
            LEFT JOIN younganimals AS ya ON cd.animalTypeID = 'atID02' AND ya.animalID = cd.animalID
            LEFT JOIN youngspecies AS ys ON cd.animalTypeID = 'atID02' AND ys.speciesID = cd.speciesID AND ys.animalID = cd.animalID
            LEFT JOIN livestock AS lv ON cd.animalTypeID = 'atID03' AND lv.animalID = cd.animalID
            LEFT JOIN livestockspecies AS lss ON cd.animalTypeID = 'atID03' AND lss.speciesID = cd.speciesID AND lss.animalID = cd.animalID
            LEFT JOIN breedingstock AS bst ON cd.animalTypeID = 'atID04' AND bst.animalID = cd.animalID
            LEFT JOIN agetype AS atg ON atg.ageID = cd.ageID AND atg.animalTypeID = cd.animalTypeID
                AND (atg.animalID IS NULL OR TRIM(atg.animalID) = '' OR atg.animalID = cd.animalID)
            LEFT JOIN age AS a ON a.ageID = cd.ageID
            LEFT JOIN gender AS g ON g.genderID = cd.genderID
            WHERE {where}
            GROUP BY cd.animalTypeID, at.animalName, cd.animalID,
                la.animalName, ya.animalName, lv.animalName, bst.animalName,
                cd.speciesID, ls.speciesName, ys.speciesName, lss.speciesName,
                cd.ageID, atg.ageName, a.ageName, cd.genderID, g.genderName
            ORDER BY animal_type, animal_name
        """)
        rows = db.execute(sql, q_params).mappings().all()
        animals = [dict(r) for r in rows]

        for a in animals:
            try: a["total_count"] = int(a.get("total_count") or 0)
            except (ValueError, TypeError): a["total_count"] = 0
            aid = (a.get("animal_type_id") or "").strip()
            cnt = a["total_count"]
            stats["total"] += cnt
            if aid == "atID01": stats["large"] += cnt
            elif aid == "atID02": stats["small"] += cnt
            elif aid == "atID03": stats["poultry"] += cnt
            elif aid == "atID04": stats["breeding"] += cnt
    except SQLAlchemyError as e:
        logger.error("Dashboard DB Error: %s", e)
    finally:
        db.close()

    return region_name, animals, stats


# ============================================================
# 🏠 ROOT & /admin
# ============================================================
@router.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    state: str = Query(None), district: str = Query(None),
    township: str = Query(None), qv: str = Query(None),
    start_date: str = Query(""), end_date: str = Query(""),
):
    user = request.session.get("user")
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={})

    role = user.get("role", "admin")
    if role == "admin":       return RedirectResponse("/system/users", status_code=303)
    if role == "enumerator":  return RedirectResponse("/survey/dashboard", status_code=303)
    if role == "staff":       return RedirectResponse("/survey/part1", status_code=303)

    region_name, animals, stats = query_dashboard_data(
        user, state, district, township, qv,
        start_date=start_date, end_date=end_date,
    )
    return templates.TemplateResponse(request=request, name="reportDashboard.html", context={
        "stats": stats, "animals": animals, "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "",
        "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "",
        "user_township_id": user.get("townshipID") or "",
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "start_date": start_date, "end_date": end_date,
        },
        "active_page": "home",
    })


@router.get("/admin")
async def admin_dashboard(
    request: Request,
    state: str = Query(None), district: str = Query(None),
    township: str = Query(None), qv: str = Query(None),
    start_date: str = Query(""), end_date: str = Query(""),
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=303)
    role = user.get("role", "admin")
    if role == "admin":       return RedirectResponse("/system/users", status_code=303)
    if role == "enumerator":  return RedirectResponse("/survey/dashboard", status_code=303)
    if role == "staff":       return RedirectResponse("/survey/part1", status_code=303)
    if role not in ("union", "state", "district", "township"):
        raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    region_name, animals, stats = query_dashboard_data(
        user, state, district, township, qv,
        start_date=start_date, end_date=end_date,
    )
    return templates.TemplateResponse(request=request, name="reportDashboard.html", context={
        "stats": stats, "animals": animals, "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "",
        "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "",
        "user_township_id": user.get("townshipID") or "",
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "start_date": start_date, "end_date": end_date,
        },
        "active_page": "home",
    })


@router.get("/report", response_class=HTMLResponse)
async def report_page_redirect(request: Request):
    from app.dependencies import get_signed_in_user
    try:
        get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin", status_code=303)