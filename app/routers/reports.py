import logging
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse


from app.constants import (
    AGE_KEY_MAP,
    ANIMAL_TYPE_NAMES,
    ANIMAL_TYPES,
    
    GENDER_KEY_MAP,
)
from app.database import get_db_connection
from app.dependencies import get_signed_in_user
from app.lookups import _get_user_state_name
from app.templating import templates
from app.district_report_excel import (
    build_district_report_workbook,
    report_date_line,
    report_year_label,
)
from app.state_report_excel import build_state_report_workbook
from app.township_report_excel import build_township_report_workbook
from app.utils import _resolve_date_range

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["reports"])


# ============================================================
# 📊 REPORT 1 — Animal counts by type/age/gender
# ============================================================
def _query_report1_one_type(cursor, animal_type_id, role, user,
                            state="", district="", township="", qv="",
                            start_date="", end_date=""):
    type_info = ANIMAL_TYPES.get(animal_type_id)
    if not type_info:
        return []
    table_name = type_info["table"]

    try:
        cursor.execute(f"SELECT animalID, animalName FROM {table_name} "
                       "WHERE animalTypeID = %s ORDER BY animalID", (animal_type_id,))
        animal_names = cursor.fetchall()
    except Exception as e:
        logger.warning("%s lookup: %s", animal_type_id, e)
        return []

    conds = ["cd.animalTypeID = %s"]
    params = [animal_type_id]
    # (role / state / district / township / qv / date filter — မပြောင်းပါ)
    if role == "state":
        conds.append("loc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s"])
        params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s", "loc.townshipID = %s"])
        params.extend([user["stateID"], user["districtID"], user["townshipID"]])
    if role in ("admin", "union") and state and state.strip():
        conds.append("loc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("loc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("loc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("loc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(loc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    where = " AND ".join(conds)
    sql = f"""
        SELECT cd.animalID AS animal_id, cd.ageID AS age_id, cd.genderID AS gender_id,
               SUM(COALESCE(cd.dataCount, 0)) AS total_count
        FROM collecteddata AS cd
        JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate
              FROM personcv) AS loc ON loc.formID = cd.formID
        WHERE {where}
        GROUP BY cd.animalID, cd.ageID, cd.genderID
    """
    cursor.execute(sql, tuple(params))
    raw = cursor.fetchall()

    age_map = AGE_KEY_MAP.get(animal_type_id, {})
    rows = {}

    # ⭐️ ကြိုတင် initialize — ဖြစ်နိုင်တဲ့ key အားလုံး ထည့်
    for a in animal_names:
        aid = a["animalID"]
        row = {
            "animalID":   aid,
            "animalName": a["animalName"],
            "total":      0,
            "combined":   0,   # ⭐️ age မပါ gender မပါ (lsID02, lsID05)
        }
        if age_map:
            for age_key in age_map.values():
                row[f"{age_key}_male"]     = 0
                row[f"{age_key}_castrated"] = 0
                row[f"{age_key}_female"]   = 0
                row[f"{age_key}_combined"] = 0  # ⭐️ age ပါ gender မပါ (ageID10)
        else:
            row["male"] = 0; row["castrated"] = 0; row["female"] = 0
        rows[aid] = row

    for item in raw:
        aid    = str(item.get("animal_id") or "").strip()
        age_id = str(item.get("age_id") or "").strip()
        gid    = str(item.get("gender_id") or "").strip()
        cnt    = int(item.get("total_count") or 0)
        if aid not in rows:
            continue

        akey = age_map.get(age_id) if age_id else None
        # In report 1, lsID03 ageID10 (under 20 weeks) belongs in the
        # first visible poultry age band. Its actual age label remains intact
        # in report 2, which displays source age groups directly.
        if (animal_type_id == "atID03" and aid == "lsID03"
                and age_id == "ageID10"):
            akey = "young"
        gkey = GENDER_KEY_MAP.get(gid) if gid else None

        # Case A — age + gender ပါ
        if akey and gkey:
            col = f"{akey}_{gkey}"
            if col in rows[aid]:
                rows[aid][col] += cnt
                rows[aid]["total"] += cnt
            continue

        # Case B — age ပါ၊ gender မပါ
        # ဥပမာ lsID03 + ageID10
        if akey and not gkey:
            # Keep age-specific counts without gender in a separate bucket.
            col = f"{akey}_combined"

            if col in rows[aid]:
                rows[aid][col] += cnt
                rows[aid]["total"] += cnt
            continue

        # Case C — age မပါ၊ gender မပါ
        # ဥပမာ lsID02, lsID05
        if not akey and not gkey:
            # ပထမဆုံး age group's ပထမဆုံး column မှာ ထည့်
            first_age_key = next(iter(age_map.values()), None)

            if first_age_key:
                col = f"{first_age_key}_combined"

                if col in rows[aid]:
                    rows[aid][col] += cnt
                    rows[aid]["total"] += cnt
            else:
                rows[aid]["combined"] += cnt
                rows[aid]["total"] += cnt

            continue

        # Case D — age မပါ၊ gender ပါ
        if not akey and gkey:
            rows[aid][gkey] = rows[aid].get(gkey, 0) + cnt
            rows[aid]["total"] += cnt
            continue


    return list(rows.values())


def _query_report1_breeding(cursor, role, user, state="", district="",
                            township="", qv="", start_date="", end_date=""):
    try:
        cursor.execute("SELECT animalID, animalName FROM breedingstock "
                       "WHERE animalTypeID = %s ORDER BY animalID", ("atID04",))
        animal_names = cursor.fetchall()
    except Exception as e:
        logger.warning("breedingstock lookup: %s", e)
        return []

    conds = ["cd.animalTypeID = %s"]
    params = ["atID04"]

    if role == "state":
        conds.append("loc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s"])
        params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s", "loc.townshipID = %s"])
        params.extend([user["stateID"], user["districtID"], user["townshipID"]])

    if role in ("admin", "union") and state and state.strip():
        conds.append("loc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("loc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("loc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("loc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(loc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    where = " AND ".join(conds)
    sql = f"""
        SELECT cd.animalID AS animal_id, cd.genderID AS gender_id,
               SUM(COALESCE(cd.dataCount, 0)) AS total_count
        FROM collecteddata AS cd
        JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate
              FROM personcv) AS loc ON loc.formID = cd.formID
        WHERE {where}
        GROUP BY cd.animalID, cd.genderID
    """
    cursor.execute(sql, tuple(params))
    raw = cursor.fetchall()

    rows = {}
    for a in animal_names:
        aid = a["animalID"]
        rows[aid] = {"animalID": aid, "animalName": a["animalName"],
                     "male": 0, "castrated": 0, "female": 0, "total": 0}

    for item in raw:
        aid = str(item.get("animal_id") or "").strip()
        gid = str(item.get("gender_id") or "").strip()
        cnt = int(item.get("total_count") or 0)
        if aid not in rows:
            continue
        gkey = GENDER_KEY_MAP.get(gid)
        if gkey in ("male", "castrated", "female"):
            rows[aid][gkey] += cnt
            rows[aid]["total"] += cnt

    return list(rows.values())


@router.get("/report/1", response_class=HTMLResponse)
async def report1_page(
    request: Request,
    state: str = Query(""), district: str = Query(""),
    township: str = Query(""), qv: str = Query(""),
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
    region_name = ""
    district_name_for_js = ""
    township_name_for_js = ""
    try:
        if role == "union":
            region_name = "တစ်နိုင်ငံလုံး"
        elif role == "state":
            state = user["stateID"] or ""
            cur.execute("SELECT stateName AS name FROM state WHERE stateID = %s",
                        (user["stateID"],))
            r = cur.fetchone()
            region_name = r["name"] if r else user["stateID"]
        elif role == "district":
            state = user["stateID"] or ""
            district = user["districtID"] or ""
            cur.execute("SELECT districtName AS name FROM district "
                        "WHERE stateID = %s AND districtID = %s",
                        (user["stateID"], user["districtID"]))
            r = cur.fetchone()
            region_name = r["name"] if r else user["districtID"]
            district_name_for_js = region_name
        elif role == "township":
            state = user["stateID"] or ""
            district = user["districtID"] or ""
            township = user["townshipID"] or ""
            cur.execute("SELECT townshipName AS name FROM township "
                        "WHERE stateID = %s AND districtID = %s AND townshipID = %s",
                        (user["stateID"], user["districtID"], user["townshipID"]))
            r = cur.fetchone()
            region_name = r["name"] if r else user["townshipID"]
            township_name_for_js = region_name
            cur.execute("SELECT districtName FROM district "
                        "WHERE stateID = %s AND districtID = %s",
                        (user["stateID"], user["districtID"]))
            d_row = cur.fetchone()
            district_name_for_js = d_row["districtName"] if d_row else ""

        large_rows    = _query_report1_one_type(cur, "atID01", role, user, state, district, township, qv, start_date, end_date)
        small_rows    = _query_report1_one_type(cur, "atID02", role, user, state, district, township, qv, start_date, end_date)
        poultry_rows  = _query_report1_one_type(cur, "atID03", role, user, state, district, township, qv, start_date, end_date)
        breeding_rows = _query_report1_breeding(cur, role, user, state, district, township, qv, start_date, end_date)
    except Exception as e:
        logger.error("Report 1 DB error: %s", e)
        large_rows = small_rows = poultry_rows = breeding_rows = []
    finally:
        cur.close(); conn.close()

    def _sum(rows): return sum((r.get("total") or 0) for r in rows)
    stats = {
        "large": _sum(large_rows), "small": _sum(small_rows),
        "poultry": _sum(poultry_rows), "breeding": _sum(breeding_rows),
    }
    stats["total"] = sum(stats.values())

    return templates.TemplateResponse(request=request, name="report1.html", context={
        "active_page": "report1", "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "",
        "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "",
        "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "",
        "user_township_name": township_name_for_js,
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "start_date": start_date, "end_date": end_date,
        },
        "large_rows": large_rows, "small_rows": small_rows,
        "poultry_rows": poultry_rows, "breeding_rows": breeding_rows,
        "stats": stats,
    })


# ============================================================
# 📈 REPORT 2 — Pivot by location
# ============================================================
def _get_animal_rows_by_type(animal_type_id: str):
    type_info = ANIMAL_TYPES.get(animal_type_id)
    if not type_info:
        return []
    table = type_info["table"]
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute(f"SELECT animalID, animalName FROM {table} "
                        "WHERE animalTypeID = %s ORDER BY animalID", (animal_type_id,))
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.warning("_get_animal_rows_by_type(%s): %s", animal_type_id, e)
        return []


def _get_species_options(animal_type_id: str, animal_id: str = ""):
    if animal_type_id not in ("atID01", "atID02", "atID03"):
        return []
    table = {"atID01": "largespecies", "atID02": "youngspecies",
             "atID03": "livestockspecies"}[animal_type_id]
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            if animal_id:
                cur.execute(f"SELECT speciesID, speciesName FROM {table} "
                            "WHERE animalID = %s ORDER BY speciesID", (animal_id,))
            else:
                cur.execute(f"SELECT DISTINCT speciesID, speciesName FROM {table} ORDER BY speciesID")
            return [{"id": str(r["speciesID"]), "name": r["speciesName"]}
                    for r in cur.fetchall()]
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.warning("_get_species_options: %s", e)
        return []


def _get_age_options(animal_type_id: str):
    if animal_type_id == "atID04":
        return []
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT ageID, ageName FROM agetype "
                        "WHERE animalTypeID = %s ORDER BY ageID", (animal_type_id,))
            seen, out = set(), []
            for r in cur.fetchall():
                if r["ageName"] in seen:
                    continue
                seen.add(r["ageName"])
                out.append({"id": str(r["ageID"]), "name": r["ageName"]})
            return out
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.warning("_get_age_options: %s", e)
        return []


def _get_gender_options(animal_type_id: str):
    if animal_type_id in ("atID03", "atID04"):
        return [{"id": "g01", "name": "အထီး"}, {"id": "g03", "name": "အမ"}]
    return [{"id": "g01", "name": "အထီး"},
            {"id": "g02", "name": "သင်းကွပ်အထီး"},
            {"id": "g03", "name": "အမ"}]


def _resolve_row_level(role: str):
    return {"union": "state", "admin": "state", "state": "district",
            "district": "township", "township": "qv"}.get(role, "state")


def _build_report2_data(role, user, animal_type_id, animal_id="", species_id="",
                        age_id="", gender_id="", start_date="", end_date=""):
    row_level = _resolve_row_level(role)
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        pc_conds = ["1=1"]; pc_params = []
        if role == "state":
            pc_conds.append("pc.stateID = %s"); pc_params.append(user["stateID"])
        elif role == "district":
            pc_conds.extend(["pc.stateID = %s", "pc.districtID = %s"])
            pc_params.extend([user["stateID"], user["districtID"]])
        elif role == "township":
            pc_conds.extend(["pc.stateID = %s", "pc.districtID = %s", "pc.townshipID = %s"])
            pc_params.extend([user["stateID"], user["districtID"], user["townshipID"]])

        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            pc_conds.append("DATE(pc.interviewDate) BETWEEN %s AND %s")
            pc_params.extend([s, e])
        pc_where = " AND ".join(pc_conds)

        cd_conds = ["cd.animalTypeID = %s"]; cd_params = [animal_type_id]
        if animal_id and str(animal_id).strip():
            cd_conds.append("cd.animalID = %s"); cd_params.append(str(animal_id).strip())
        if species_id and str(species_id).strip():
            cd_conds.append("cd.speciesID = %s"); cd_params.append(str(species_id).strip())
        if age_id and str(age_id).strip():
            cd_conds.append("cd.ageID = %s"); cd_params.append(str(age_id).strip())
        if gender_id and str(gender_id).strip():
            cd_conds.append("cd.genderID = %s"); cd_params.append(str(gender_id).strip())
        cd_where = " AND ".join(cd_conds)
        all_params = tuple(pc_params + cd_params)

        if row_level == "state":
            row_id_expr = "pc.stateID"
            row_name_expr = "COALESCE(st.stateName, pc.stateID)"
            row_joins = "LEFT JOIN state AS st ON st.stateID = pc.stateID"
        elif row_level == "district":
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID)"
            row_name_expr = "COALESCE(dt.districtName, pc.districtID)"
            row_joins = "LEFT JOIN district AS dt ON dt.stateID = pc.stateID AND dt.districtID = pc.districtID"
        elif row_level == "township":
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID, '|', pc.townshipID)"
            row_name_expr = "COALESCE(ts.townshipName, pc.townshipID)"
            row_joins = ("LEFT JOIN township AS ts ON ts.stateID = pc.stateID "
                         "AND ts.districtID = pc.districtID AND ts.townshipID = pc.townshipID")
        else:
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID, '|', pc.townshipID, '|', pc.QVID)"
            row_name_expr = "COALESCE(qv.QVName, pc.QVID)"
            row_joins = ("LEFT JOIN qv ON qv.stateID = pc.stateID "
                         "AND qv.districtID = pc.districtID "
                         "AND qv.townshipID = pc.townshipID AND qv.QVID = pc.QVID")

        col_sql = f"""
            SELECT DISTINCT cd.animalID AS animal_id, cd.speciesID AS species_id, cd.ageID AS age_id
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            WHERE {pc_where} AND {cd_where}
            ORDER BY cd.animalID, cd.speciesID, cd.ageID
        """
        cur.execute(col_sql, all_params)
        col_rows = cur.fetchall()
        if not col_rows:
            cur.close(); conn.close()
            return [], [], 0, row_level

        def _lookup_animal_name(atid, aid):
            try:
                table = {"atID01": "largeanimals", "atID02": "younganimals",
                         "atID03": "livestock"}.get(atid, "breedingstock")
                cur.execute(f"SELECT animalName FROM {table} WHERE animalID = %s", (aid,))
                r = cur.fetchone()
                return r["animalName"] if r else str(aid)
            except Exception:
                return str(aid)

        def _lookup_species_name(atid, aid, spid):
            if atid not in ("atID01", "atID02", "atID03"):
                return str(spid)
            table = {"atID01": "largespecies", "atID02": "youngspecies",
                     "atID03": "livestockspecies"}[atid]
            try:
                cur.execute(f"SELECT speciesName FROM {table} "
                            "WHERE speciesID = %s AND animalID = %s", (spid, aid))
                r = cur.fetchone()
                return r["speciesName"] if r else str(spid)
            except Exception:
                return str(spid)

        def _lookup_age_name(atid, aid, ageid):
            try:
                cur.execute("SELECT ageName FROM agetype WHERE ageID = %s "
                            "AND animalTypeID = %s "
                            "AND (animalID IS NULL OR TRIM(animalID) = '' OR animalID = %s)",
                            (ageid, atid, aid))
                r = cur.fetchone()
                if r:
                    return r["ageName"]
                cur.execute("SELECT ageName FROM age WHERE ageID = %s", (ageid,))
                r = cur.fetchone()
                return r["ageName"] if r else str(ageid)
            except Exception:
                return str(ageid)

        genders_for_col = _get_gender_options(animal_type_id)
        gender_names = {g["id"]: g["name"] for g in genders_for_col}
        gender_order = [g["id"] for g in genders_for_col]

        column_groups = []
        seen_keys = set()
        for r in col_rows:
            aid = str(r["animal_id"] or "")
            spid = str(r["species_id"] or "")
            ageid = str(r["age_id"] or "")
            key = (aid, spid, ageid)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            column_groups.append({
                "animal_id": aid,
                "animal_name": _lookup_animal_name(animal_type_id, aid),
                "species_id": spid,
                "species_name": _lookup_species_name(animal_type_id, aid, spid),
                "age_id": ageid,
                "age_name": _lookup_age_name(animal_type_id, aid, ageid),
                "genders": [{"id": gid, "name": gender_names[gid]} for gid in gender_order],
            })

        data_sql = f"""
            SELECT {row_id_expr} AS row_id, {row_name_expr} AS row_name,
                cd.animalID AS animal_id, cd.speciesID AS species_id,
                cd.ageID AS age_id, cd.genderID AS gender_id,
                SUM(COALESCE(cd.dataCount, 0)) AS total_count
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            {row_joins}
            WHERE {pc_where} AND {cd_where}
            GROUP BY {row_id_expr}, {row_name_expr}, cd.animalID, cd.speciesID, cd.ageID, cd.genderID
            ORDER BY row_name, cd.animalID, cd.speciesID, cd.ageID, cd.genderID
        """
        cur.execute(data_sql, all_params)
        data_rows = cur.fetchall()

        total_sql = f"""
            SELECT {row_id_expr} AS row_id, {row_name_expr} AS row_name,
                   SUM(COALESCE(cd.dataCount, 0)) AS row_total
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            {row_joins}
            WHERE {pc_where} AND {cd_where}
            GROUP BY {row_id_expr}, {row_name_expr}
            ORDER BY row_name
        """
        cur.execute(total_sql, all_params)
        total_rows = cur.fetchall()
        cur.close(); conn.close()

        cell_map = {}; row_names = {}
        for d in data_rows:
            rid = str(d["row_id"] or "")
            row_names[rid] = d["row_name"] or rid
            key = (rid, str(d["animal_id"] or ""),
                   str(d["species_id"] or ""), str(d["age_id"] or ""))
            cell_map.setdefault(key, {})
            cell_map[key][str(d["gender_id"] or "")] = int(d["total_count"] or 0)

        row_totals = {}
        for d in total_rows:
            rid = str(d["row_id"] or "")
            row_names.setdefault(rid, d["row_name"] or rid)
            row_totals[rid] = int(d["row_total"] or 0)

        report_rows = []
        grand_total = 0
        for rid in sorted(row_names.keys(), key=lambda x: (row_names[x] or x)):
            cells = []
            for cg in column_groups:
                key = (rid, cg["animal_id"], cg["species_id"], cg["age_id"])
                gender_map = cell_map.get(key, {})
                gender_values = []
                group_total = 0
                for g in cg["genders"]:
                    v = int(gender_map.get(g["id"], 0))
                    gender_values.append({"gender_id": g["id"], "value": v})
                    group_total += v
                cells.append({"group_total": group_total, "gender_values": gender_values})
            rt = row_totals.get(rid, 0)
            grand_total += rt
            report_rows.append({"row_id": rid, "row_name": row_names.get(rid, rid),
                                "cells": cells, "row_total": rt})

        return column_groups, report_rows, grand_total, row_level
    except Exception as e:
        logger.error("Report2 DB Error: %s", e)
        return [], [], 0, _resolve_row_level(role)


@router.get("/report/2", response_class=HTMLResponse)
async def report2_page(
    request: Request,
    animal_type: str = Query("atID01"), animal: str = Query(""),
    species: str = Query(""), age: str = Query(""), gender: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"):
        raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    if animal_type not in ANIMAL_TYPES:
        animal_type = "atID01"
    animal_type_name = next((a["name"] for a in ANIMAL_TYPE_NAMES
                             if a["id"] == animal_type), "တိရိစ္ဆာန်")

    animal_rows = _get_animal_rows_by_type(animal_type)
    filter_species = _get_species_options(animal_type, animal) if animal_type != "atID04" else []
    filter_ages = _get_age_options(animal_type) if animal_type != "atID04" else []
    filter_genders = _get_gender_options(animal_type)

    column_groups, report_rows, grand_total, row_level = _build_report2_data(
        role, user, animal_type,
        animal_id=animal, species_id=species, age_id=age, gender_id=gender,
        start_date=start_date, end_date=end_date,
    )

    region_name = "တစ်နိုင်ငံလုံး" if role == "union" else _get_user_state_name(user)
    district_name_for_js = ""
    township_name_for_js = ""
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            if user.get("districtID"):
                cur.execute("SELECT districtName FROM district "
                            "WHERE stateID = %s AND districtID = %s",
                            (user.get("stateID"), user.get("districtID")))
                r = cur.fetchone()
                district_name_for_js = r["districtName"] if r else ""
            if user.get("townshipID"):
                cur.execute("SELECT townshipName FROM township "
                            "WHERE stateID = %s AND districtID = %s AND townshipID = %s",
                            (user.get("stateID"), user.get("districtID"),
                             user.get("townshipID")))
                r = cur.fetchone()
                township_name_for_js = r["townshipName"] if r else ""
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.warning("report2 names lookup failed: %s", e)

    return templates.TemplateResponse(request=request, name="report2.html", context={
        "active_page": "report2", "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "",
        "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "",
        "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "",
        "user_township_name": township_name_for_js,
        "animal_type": animal_type, "animal_type_name": animal_type_name,
        "animal_types": ANIMAL_TYPE_NAMES,
        "animal_rows": animal_rows,
        "filter_species": filter_species, "filter_ages": filter_ages,
        "filter_genders": filter_genders,
        "selected_animal": animal, "selected_species": species,
        "selected_age": age, "selected_gender": gender,
        "column_groups": column_groups, "report_rows": report_rows,
        "grand_total": grand_total, "row_level": row_level,
        "filters": {"state": "", "district": "", "township": "", "qv": "",
                    "animal_type": animal_type,
                    "start_date": start_date, "end_date": end_date},
    })


@router.get("/api/report2/options")
async def report2_options(request: Request, animal_type: str = Query("atID01")):
    try:
        get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    if animal_type not in ANIMAL_TYPES:
        animal_type = "atID01"
    species = _get_species_options(animal_type) if animal_type != "atID04" else []
    ages = _get_age_options(animal_type) if animal_type != "atID04" else []
    genders = _get_gender_options(animal_type)
    return {"species": species, "ages": ages, "genders": genders}


# ============================================================
# 🏘️ TOWNSHIP REPORT — village/ward household counts
# ============================================================
def _township_report_scope(user: dict) -> tuple[str, str, str]:
    role = str(user.get("role") or "").strip().lower()
    if role != "township":
        raise HTTPException(
            403,
            "ဤစာမျက်နှာကို မြို့နယ်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။",
        )

    state_id = str(user.get("stateID") or "").strip()
    district_id = str(user.get("districtID") or "").strip()
    township_id = str(user.get("townshipID") or "").strip()
    if not all((state_id, district_id, township_id)):
        raise HTTPException(
            403,
            "သင့်အကောင့်တွင် သတ်မှတ်ထားသော နယ်မြေအချက်အလက် မပြည့်စုံပါ။",
        )
    return state_id, district_id, township_id


def _query_township_village_report(cursor, state_id: str, district_id: str,
                                   township_id: str, start_date: str = "",
                                   end_date: str = "") -> list[dict]:
    """One row per village that has matching completed household records.

    Villages that only exist in the ``village`` table (with no matching
    ``personcv`` records) are intentionally excluded.  ``personcv.WardName``
    normally contains the villageID; the villageName comparison keeps older
    rows (which stored the name) visible as well.
    """
    start, end = _resolve_date_range(start_date, end_date)
    date_join = ""
    params: list = []
    if start and end:
        date_join = " AND DATE(pc.interviewDate) BETWEEN %s AND %s"
        params.extend([start, end])
    params.extend([state_id, district_id, township_id])

    cursor.execute(
        f"""
        SELECT v.QVID, v.villageID, v.villageName,
               COALESCE(q.QVName, v.QVID) AS QVName,
               COUNT(pc.formID) AS household_count
        FROM village AS v
        LEFT JOIN qv AS q
               ON q.stateID = v.stateID
              AND q.districtID = v.districtID
              AND q.townshipID = v.townshipID
              AND q.QVID = v.QVID
        JOIN personcv AS pc
               ON pc.stateID = v.stateID
              AND pc.districtID = v.districtID
              AND pc.townshipID = v.townshipID
              AND pc.QVID = v.QVID
              AND (pc.WardName = v.villageID OR pc.WardName = v.villageName)
              AND pc.status = 1
              {date_join}
        WHERE v.stateID = %s
          AND v.districtID = %s
          AND v.townshipID = %s
        GROUP BY v.QVID, v.villageID, v.villageName, q.QVName
        ORDER BY COALESCE(q.QVName, v.QVID), v.villageName
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _get_township_report_place(cursor, state_id: str, district_id: str,
                               township_id: str) -> tuple[str, str, str]:
    cursor.execute(
        """
        SELECT st.stateName AS state_name,
               dt.districtName AS district_name,
               ts.townshipName AS township_name
        FROM township AS ts
        LEFT JOIN district AS dt
               ON dt.stateID = ts.stateID
              AND dt.districtID = ts.districtID
        LEFT JOIN state AS st ON st.stateID = ts.stateID
        WHERE ts.stateID = %s
          AND ts.districtID = %s
          AND ts.townshipID = %s
        LIMIT 1
        """,
        (state_id, district_id, township_id),
    )
    place = cursor.fetchone() or {}
    return (
        place.get("state_name") or state_id,
        place.get("district_name") or district_id,
        place.get("township_name") or township_id,
    )


@router.get("/township/report", response_class=HTMLResponse)
async def township_report_page(
    request: Request,
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id, district_id, township_id = _township_report_scope(user)

    villages: list[dict] = []
    state_name = state_id
    district_name = district_id
    township_name = township_id
    error = None

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        state_name, district_name, township_name = _get_township_report_place(
            cursor, state_id, district_id, township_id,
        )

        villages = _query_township_village_report(
            cursor, state_id, district_id, township_id, start_date, end_date,
        )
    except Exception:
        logger.exception("Township report DB error")
        error = "အစီရင်ခံစာ ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
        villages = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_households = sum(int(row.get("household_count") or 0) for row in villages)

    return templates.TemplateResponse(request=request, name="townshipReport.html", context={
        "active_page": "township_report",
        "role": "township",
        "user": user,
        "state_id": state_id,
        "district_id": district_id,
        "township_id": township_id,
        "state_name": state_name,
        "district_name": district_name,
        "township_name": township_name,
        "region_name": township_name,
        "villages": villages,
        "total_villages": len(villages),
        "total_households": total_households,
        "filters": {"start_date": start_date, "end_date": end_date},
        "error": error,
    })


@router.get("/township/report/export")
async def township_report_export(
    request: Request,
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id, district_id, township_id = _township_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        state_name, district_name, township_name = _get_township_report_place(
            cursor, state_id, district_id, township_id,
        )
        villages = _query_township_village_report(
            cursor, state_id, district_id, township_id, start_date, end_date,
        )
        output = build_township_report_workbook(
            villages, state_name, district_name, township_name,
            start_date, end_date,
        )
    except Exception:
        logger.exception("Township report export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_Township_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# 🏛️ DISTRICT REPORT — township village counts + township summary
# ============================================================
def _district_report_scope(user: dict) -> tuple[str, str]:
    role = str(user.get("role") or "").strip().lower()
    if role != "district":
        raise HTTPException(
            403,
            "ဤစာမျက်နှာကို ခရိုင်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။",
        )

    state_id = str(user.get("stateID") or "").strip()
    district_id = str(user.get("districtID") or "").strip()
    if not all((state_id, district_id)):
        raise HTTPException(
            403,
            "သင့်အကောင့်တွင် သတ်မှတ်ထားသော နယ်မြေအချက်အလက် မပြည့်စုံပါ။",
        )
    return state_id, district_id


def _get_district_report_place(cursor, state_id: str,
                               district_id: str) -> tuple[str, str]:
    cursor.execute(
        """
        SELECT st.stateName AS state_name,
               dt.districtName AS district_name
        FROM district AS dt
        LEFT JOIN state AS st ON st.stateID = dt.stateID
        WHERE dt.stateID = %s
          AND dt.districtID = %s
        LIMIT 1
        """,
        (state_id, district_id),
    )
    place = cursor.fetchone() or {}
    return (
        place.get("state_name") or state_id,
        place.get("district_name") or district_id,
    )


def _get_district_report_townships(cursor, state_id: str,
                                   district_id: str) -> list[dict]:
    cursor.execute(
        """
        SELECT townshipID, townshipName
        FROM township
        WHERE stateID = %s AND districtID = %s
        ORDER BY townshipName, townshipID
        """,
        (state_id, district_id),
    )
    return cursor.fetchall()


def _resolve_district_township(townships: list[dict], requested: str) -> str:
    requested = (requested or "").strip()
    if requested:
        for township in townships:
            if str(township.get("townshipID") or "") == requested:
                return requested
    if townships:
        return str(townships[0].get("townshipID") or "")
    return ""


def _query_district_township_summary(cursor, state_id: str, district_id: str,
                                     start_date: str = "",
                                     end_date: str = "",
                                     township_id: str = "") -> list[dict]:
    """One row per township, using only township and completed personcv rows.

    A township is counted even when it has no completed survey records; its
    three numeric columns are then zero.  The ward column counts distinct
    QV IDs (wards/village tracts) and the village column counts distinct
    WardName values stored by the survey.
    """
    start, end = _resolve_date_range(start_date, end_date)
    date_join = ""
    params: list = []
    if start and end:
        date_join = " AND DATE(pc.interviewDate) BETWEEN %s AND %s"
        params.extend([start, end])
    params.extend([state_id, district_id])
    township_cond = ""
    if township_id:
        township_cond = " AND ts.townshipID = %s"
        params.append(township_id)

    cursor.execute(
        f"""
        SELECT ts.townshipID, ts.townshipName,
               COUNT(DISTINCT pc.QVID) AS ward_count,
               COUNT(DISTINCT NULLIF(TRIM(pc.WardName), '')) AS village_count,
               COUNT(pc.formID) AS household_count
        FROM township AS ts
        LEFT JOIN personcv AS pc
               ON pc.stateID = ts.stateID
              AND pc.districtID = ts.districtID
              AND pc.townshipID = ts.townshipID
              AND pc.status = 1
              {date_join}
        WHERE ts.stateID = %s
          AND ts.districtID = %s
          {township_cond}
        GROUP BY ts.townshipID, ts.townshipName
        ORDER BY ts.townshipName, ts.townshipID
        """,
        tuple(params),
    )
    return cursor.fetchall()


@router.get("/district/report", response_class=HTMLResponse)
async def district_report_page(
    request: Request,
    view: str = Query("village"),
    township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id, district_id = _district_report_scope(user)
    active_view = "summary" if str(view or "").strip().lower() == "summary" else "village"

    state_name = state_id
    district_name = district_id
    townships: list[dict] = []
    selected_township = ""
    selected_township_name = ""
    villages: list[dict] = []
    summary_rows: list[dict] = []
    summary_totals = {"ward_count": 0, "village_count": 0, "household_count": 0}
    error = None

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        state_name, district_name = _get_district_report_place(
            cursor, state_id, district_id,
        )
        townships = _get_district_report_townships(cursor, state_id, district_id)
        selected_township = _resolve_district_township(townships, township)
        if selected_township:
            selected_township_name = next(
                (str(row.get("townshipName") or selected_township)
                 for row in townships
                 if str(row.get("townshipID") or "") == selected_township),
                selected_township,
            )

        if active_view == "village":
            if selected_township:
                villages = _query_township_village_report(
                    cursor, state_id, district_id, selected_township,
                    start_date, end_date,
                )
        else:
            summary_rows = _query_district_township_summary(
                cursor, state_id, district_id, start_date, end_date,
            )
            for row in summary_rows:
                summary_totals["ward_count"] += int(row.get("ward_count") or 0)
                summary_totals["village_count"] += int(row.get("village_count") or 0)
                summary_totals["household_count"] += int(row.get("household_count") or 0)
    except Exception:
        logger.exception("District report DB error")
        error = "အစီရင်ခံစာ ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
        villages = []
        summary_rows = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_households = sum(int(row.get("household_count") or 0) for row in villages)

    return templates.TemplateResponse(request=request, name="districtReport.html", context={
        "active_page": "district_report",
        "role": "district",
        "user": user,
        "view": active_view,
        "state_id": state_id,
        "district_id": district_id,
        "township_id": selected_township,
        "state_name": state_name,
        "district_name": district_name,
        "township_name": selected_township_name,
        "region_name": district_name,
        "townships": townships,
        "selected_township": selected_township,
        "villages": villages,
        "summary_rows": summary_rows,
        "summary_totals": summary_totals,
        "total_villages": len(villages),
        "total_households": total_households,
        "report_year": report_year_label(start_date, end_date),
        "report_date_line": report_date_line(start_date, end_date),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "township": selected_township,
            "view": active_view,
        },
        "error": error,
    })


@router.get("/district/report/export")
async def district_report_export(
    request: Request,
    township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id, district_id = _district_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        townships = _get_district_report_townships(cursor, state_id, district_id)
        selected_township = _resolve_district_township(townships, township)
        if not selected_township:
            raise HTTPException(400, "ခရိုင်အတွင်း မြို့နယ်များ မရှိပါ။")

        _, _, township_name = _get_township_report_place(
            cursor, state_id, district_id, selected_township,
        )
        state_name, district_name = _get_district_report_place(
            cursor, state_id, district_id,
        )
        villages = _query_township_village_report(
            cursor, state_id, district_id, selected_township,
            start_date, end_date,
        )
        output = build_township_report_workbook(
            villages, state_name, district_name, township_name,
            start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("District report export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_District_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/district/report/summary/export")
async def district_report_summary_export(
    request: Request,
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id, district_id = _district_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        state_name, district_name = _get_district_report_place(
            cursor, state_id, district_id,
        )
        summary_rows = _query_district_township_summary(
            cursor, state_id, district_id, start_date, end_date,
        )
        output = build_district_report_workbook(
            summary_rows, state_name, district_name,
            start_date, end_date,
        )
    except Exception:
        logger.exception("District summary report export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_District_Summary_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# 🏛️ STATE REPORT — village, district summary, state summary
# ============================================================
def _state_report_scope(user: dict) -> str:
    role = str(user.get("role") or "").strip().lower()
    if role != "state":
        raise HTTPException(
            403,
            "ဤစာမျက်နှာကို တိုင်းဒေသကြီး/ပြည်နယ်အသုံးပြုသူများသာ ကြည့်ခွင့်ရှိပါသည်။",
        )

    state_id = str(user.get("stateID") or "").strip()
    if not state_id:
        raise HTTPException(
            403,
            "သင့်အကောင့်တွင် သတ်မှတ်ထားသော နယ်မြေအချက်အလက် မပြည့်စုံပါ။",
        )
    return state_id


def _get_state_report_place(cursor, state_id: str) -> str:
    cursor.execute(
        "SELECT stateName FROM state WHERE stateID = %s LIMIT 1",
        (state_id,),
    )
    place = cursor.fetchone() or {}
    return str(place.get("stateName") or state_id)


def _get_state_report_districts(cursor, state_id: str) -> list[dict]:
    cursor.execute(
        """
        SELECT districtID, districtName
        FROM district
        WHERE stateID = %s
        ORDER BY districtName, districtID
        """,
        (state_id,),
    )
    return cursor.fetchall()


def _get_state_report_townships(cursor, state_id: str = "",
                                district_id: str = "") -> list[dict]:
    state_cond = ""
    district_cond = ""
    params: list = []
    if state_id:
        state_cond = " AND ts.stateID = %s"
        params.append(state_id)
    if district_id:
        district_cond = " AND ts.districtID = %s"
        params.append(district_id)

    cursor.execute(
        f"""
        SELECT ts.townshipID, ts.townshipName, ts.districtID, ts.stateID,
               COALESCE(dt.districtName, ts.districtID) AS districtName
        FROM township AS ts
        LEFT JOIN district AS dt
               ON dt.stateID = ts.stateID
              AND dt.districtID = ts.districtID
        WHERE 1=1
          {state_cond}
          {district_cond}
        ORDER BY dt.districtName, ts.townshipName, ts.townshipID
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _resolve_state_district(districts: list[dict], requested: str) -> str:
    requested = (requested or "").strip()
    if requested:
        for district in districts:
            if str(district.get("districtID") or "") == requested:
                return requested
    if districts:
        return str(districts[0].get("districtID") or "")
    return ""


def _resolve_state_township(townships: list[dict], requested: str,
                            default_first: bool = False) -> str:
    requested = (requested or "").strip()
    if requested:
        for township in townships:
            if str(township.get("townshipID") or "") == requested:
                return requested
    if default_first and townships:
        return str(townships[0].get("townshipID") or "")
    return ""


def _query_state_township_summary(cursor, state_id: str, district_id: str = "",
                                  township_id: str = "", start_date: str = "",
                                  end_date: str = "") -> list[dict]:
    """One row per township across the state, including zero-count townships."""
    start, end = _resolve_date_range(start_date, end_date)
    date_join = ""
    params: list = []
    if start and end:
        date_join = " AND DATE(pc.interviewDate) BETWEEN %s AND %s"
        params.extend([start, end])

    conds = ["ts.stateID = %s"]
    params.append(state_id)
    if district_id:
        conds.append("ts.districtID = %s")
        params.append(district_id)
    if township_id:
        conds.append("ts.townshipID = %s")
        params.append(township_id)
    where_clause = " AND ".join(conds)

    cursor.execute(
        f"""
        SELECT ts.districtID,
               COALESCE(dt.districtName, ts.districtID) AS districtName,
               ts.townshipID, ts.townshipName,
               COUNT(DISTINCT pc.QVID) AS ward_count,
               COUNT(DISTINCT NULLIF(TRIM(pc.WardName), '')) AS village_count,
               COUNT(pc.formID) AS household_count
        FROM township AS ts
        LEFT JOIN district AS dt
               ON dt.stateID = ts.stateID
              AND dt.districtID = ts.districtID
        LEFT JOIN personcv AS pc
               ON pc.stateID = ts.stateID
              AND pc.districtID = ts.districtID
              AND pc.townshipID = ts.townshipID
              AND pc.status = 1
              {date_join}
        WHERE {where_clause}
        GROUP BY ts.districtID, dt.districtName,
                 ts.townshipID, ts.townshipName
        ORDER BY dt.districtName, ts.townshipName, ts.townshipID
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _state_report_link(view: str, district: str = "", township: str = "",
                       start_date: str = "", end_date: str = "") -> str:
    params = {"view": view}
    if district:
        params["district"] = district
    if township:
        params["township"] = township
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return "/state/report?" + urlencode(params)


@router.get("/state/report", response_class=HTMLResponse)
async def state_report_page(
    request: Request,
    view: str = Query("village"),
    district: str = Query(""),
    township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id = _state_report_scope(user)
    active_view = str(view or "").strip().lower()
    if active_view not in ("village", "district", "state"):
        active_view = "village"

    state_name = state_id
    district_name = ""
    township_name = ""
    districts: list[dict] = []
    townships: list[dict] = []
    filter_townships: list[dict] = []
    selected_district = ""
    selected_township = ""
    villages: list[dict] = []
    summary_rows: list[dict] = []
    summary_totals = {"ward_count": 0, "village_count": 0, "household_count": 0}
    error = None

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        state_name = _get_state_report_place(cursor, state_id)
        districts = _get_state_report_districts(cursor, state_id)

        if active_view == "state":
            selected_district = _resolve_state_district(districts, district) \
                if (district or "").strip() else ""
        else:
            selected_district = _resolve_state_district(districts, district)

        filter_townships = _get_state_report_townships(cursor, state_id)
        townships = [
            row for row in filter_townships
            if selected_district
            and str(row.get("districtID") or "") == selected_district
        ]

        if active_view == "village":
            selected_township = _resolve_state_township(
                townships, township, default_first=True,
            )
        elif not selected_district:
            selected_township = ""
        else:
            selected_township = _resolve_state_township(townships, township)

        selected_district_row = next(
            (row for row in districts
             if str(row.get("districtID") or "") == selected_district),
            None,
        )
        if selected_district_row:
            district_name = str(
                selected_district_row.get("districtName") or selected_district
            )
        elif active_view == "state":
            district_name = "ခရိုင်အားလုံး"

        selected_township_row = next(
            (row for row in townships
             if str(row.get("townshipID") or "") == selected_township),
            None,
        )
        if selected_township_row:
            township_name = str(
                selected_township_row.get("townshipName") or selected_township
            )
        elif active_view in ("district", "state"):
            township_name = "မြို့နယ်အားလုံး"

        if active_view == "village":
            if selected_district and selected_township:
                villages = _query_township_village_report(
                    cursor, state_id, selected_district, selected_township,
                    start_date, end_date,
                )
        elif active_view == "district":
            if selected_district:
                summary_rows = _query_district_township_summary(
                    cursor, state_id, selected_district,
                    start_date, end_date, selected_township,
                )
        else:
            summary_rows = _query_state_township_summary(
                cursor, state_id, selected_district, selected_township,
                start_date, end_date,
            )

        if active_view != "village":
            for row in summary_rows:
                summary_totals["ward_count"] += int(row.get("ward_count") or 0)
                summary_totals["village_count"] += int(row.get("village_count") or 0)
                summary_totals["household_count"] += int(row.get("household_count") or 0)
    except Exception:
        logger.exception("State report DB error")
        error = "အစီရင်ခံစာ ရယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။"
        villages = []
        summary_rows = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_households = sum(int(row.get("household_count") or 0) for row in villages)
    summary_district_count = len({
        str(row.get("districtID") or "") for row in summary_rows
    })
    summary_township_count = len(summary_rows)

    first_district = str(districts[0].get("districtID") or "") if districts else ""
    village_district = selected_district
    if not village_district and selected_township:
        selected_township_scope = next(
            (row for row in townships
             if str(row.get("townshipID") or "") == selected_township),
            None,
        )
        if selected_township_scope:
            village_district = str(selected_township_scope.get("districtID") or "")
    if not village_district:
        village_district = first_district

    village_township = selected_township
    if not village_township:
        village_township = next(
            (str(row.get("townshipID") or "") for row in filter_townships
             if str(row.get("districtID") or "") == village_district),
            "",
        )

    district_tab = selected_district or first_district
    view_links = {
        "village": _state_report_link(
            "village", village_district, village_township,
            start_date, end_date,
        ),
        "district": _state_report_link(
            "district", district_tab, "", start_date, end_date,
        ),
        "state": _state_report_link(
            "state",
            selected_district if active_view == "state" else "",
            selected_township if active_view == "state" else "",
            start_date, end_date,
        ),
    }

    return templates.TemplateResponse(request=request, name="stateReport.html", context={
        "active_page": "state_report",
        "role": "state",
        "user": user,
        "view": active_view,
        "state_id": state_id,
        "district_id": selected_district,
        "township_id": selected_township,
        "state_name": state_name,
        "district_name": district_name,
        "township_name": township_name,
        "region_name": state_name,
        "districts": districts,
        "townships": townships,
        "filter_townships": filter_townships,
        "selected_district": selected_district,
        "selected_township": selected_township,
        "villages": villages,
        "summary_rows": summary_rows,
        "summary_totals": summary_totals,
        "summary_district_count": summary_district_count,
        "summary_township_count": summary_township_count,
        "total_villages": len(villages),
        "total_households": total_households,
        "report_year": report_year_label(start_date, end_date),
        "report_date_line": report_date_line(start_date, end_date),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "district": selected_district,
            "township": selected_township,
            "view": active_view,
        },
        "view_links": view_links,
        "error": error,
    })


def _get_all_states(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT stateID, stateName
        FROM state
        ORDER BY stateName, stateID
        """
    )
    return cursor.fetchall()


def _get_all_districts(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT districtID, districtName, stateID
        FROM district
        ORDER BY stateID, districtName, districtID
        """
    )
    return cursor.fetchall()


def _resolve_state_report_state(states: list[dict], requested: str) -> str:
    requested = (requested or "").strip()
    if requested:
        for st in states:
            if str(st.get("stateID") or "") == requested:
                return requested
    if states:
        return str(states[0].get("stateID") or "")
    return ""


@router.get("/union/report", response_class=HTMLResponse)
async def union_report_page(
    request: Request,
    view: str = Query("village"),
    state: str = Query(""),
    district: str = Query(""),
    township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = str(user.get("role") or "").strip().lower()
    if role != "union":
        raise HTTPException(
            403,
            "This report page is for union users only.",
        )

    active_view = str(view or "").strip().lower()
    if active_view not in ("village", "district", "state"):
        active_view = "village"

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        states = _get_all_states(cursor)
        selected_state = _resolve_state_report_state(states, state)

        state_name = ""
        state_row = next(
            (st for st in states if str(st.get("stateID") or "") == selected_state),
            None,
        )
        if state_row:
            state_name = str(state_row.get("stateName") or selected_state)
        elif states:
            state_name = str(states[0].get("stateName") or states[0].get("stateID"))

        districts = _get_state_report_districts(cursor, selected_state) if selected_state else []
        all_districts = _get_all_districts(cursor)
        filter_townships = _get_state_report_townships(cursor)

        if active_view == "state":
            selected_district = _resolve_state_district(districts, district) \
                if (district or "").strip() else ""
        else:
            selected_district = _resolve_state_district(districts, district)

        townships = [
            row for row in filter_townships
            if selected_district and str(row.get("districtID") or "") == selected_district
            and str(row.get("stateID") or "") == selected_state
        ]

        if active_view == "village":
            selected_township = _resolve_state_township(
                townships, township, default_first=True,
            )
        elif not selected_district:
            selected_township = ""
        else:
            selected_township = _resolve_state_township(townships, township)

        selected_district_row = next(
            (row for row in districts if str(row.get("districtID") or "") == selected_district),
            None,
        )
        if selected_district_row:
            district_name = str(
                selected_district_row.get("districtName") or selected_district
            )
        elif active_view == "state":
            district_name = "ခရိုင်အားလုံး"
        else:
            district_name = ""

        selected_township_row = next(
            (row for row in townships if str(row.get("townshipID") or "") == selected_township),
            None,
        )
        if selected_township_row:
            township_name = str(
                selected_township_row.get("townshipName") or selected_township
            )
        elif active_view in ("district", "state"):
            township_name = "မြို့နယ်အားလုံး"
        else:
            township_name = ""

        villages: list[dict] = []
        summary_rows: list[dict] = []
        summary_totals = {"ward_count": 0, "village_count": 0, "household_count": 0}
        error = None

        if active_view == "village":
            if selected_state and selected_district and selected_township:
                villages = _query_township_village_report(
                    cursor, selected_state, selected_district, selected_township,
                    start_date, end_date,
                )
        elif active_view == "district":
            if selected_state and selected_district:
                summary_rows = _query_district_township_summary(
                    cursor, selected_state, selected_district,
                    start_date, end_date, selected_township,
                )
        else:
            if selected_state:
                summary_rows = _query_state_township_summary(
                    cursor, selected_state, selected_district, selected_township,
                    start_date, end_date,
                )

        if active_view != "village":
            for row in summary_rows:
                summary_totals["ward_count"] += int(row.get("ward_count") or 0)
                summary_totals["village_count"] += int(row.get("village_count") or 0)
                summary_totals["household_count"] += int(row.get("household_count") or 0)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Union report DB error")
        error = "Unable to load the union report. Please try again later."
        villages = []
        summary_rows = []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_households = sum(int(row.get("household_count") or 0) for row in villages)
    summary_district_count = len({str(row.get("districtID") or "") for row in summary_rows})
    summary_township_count = len(summary_rows)

    first_district = str(districts[0].get("districtID") or "") if districts else ""
    village_district = selected_district or first_district
    village_township = selected_township
    if not village_township and selected_state:
        village_township = next(
            (str(row.get("townshipID") or "") for row in filter_townships
             if str(row.get("districtID") or "") == village_district),
            "",
        )

    def _union_report_link(view_name: str, state_id: str = "", district_id: str = "",
                           township_id: str = "", start_date: str = "", end_date: str = "") -> str:
        params = {"view": view_name, "state": state_id}
        if district_id:
            params["district"] = district_id
        if township_id:
            params["township"] = township_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return "/union/report?" + urlencode(params)

    district_tab = selected_district or first_district
    view_links = {
        "village": _union_report_link(
            "village", selected_state, village_district, village_township,
            start_date, end_date,
        ),
        "district": _union_report_link(
            "district", selected_state, district_tab, "", start_date, end_date,
        ),
        "state": _union_report_link(
            "state",
            selected_state if active_view == "state" else "",
            selected_district if active_view == "state" else "",
            selected_township if active_view == "state" else "",
            start_date, end_date,
        ),
    }

    return templates.TemplateResponse(request=request, name="stateReport.html", context={
        "active_page": "union_report",
        "role": "union",
        "user": user,
        "view": active_view,
        "state_id": selected_state,
        "district_id": selected_district,
        "township_id": selected_township,
        "state_name": state_name,
        "district_name": district_name,
        "township_name": township_name,
        "region_name": state_name,
        "states": states,
        "selected_state": selected_state,
        "districts": districts,
        "townships": townships,
        "filter_townships": filter_townships,
        "selected_district": selected_district,
        "selected_township": selected_township,
        "villages": villages,
        "summary_rows": summary_rows,
        "summary_totals": summary_totals,
        "summary_district_count": summary_district_count,
        "summary_township_count": summary_township_count,
        "total_villages": len(villages),
        "total_households": total_households,
        "report_year": report_year_label(start_date, end_date),
        "report_date_line": report_date_line(start_date, end_date),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "state": selected_state,
            "district": selected_district,
            "township": selected_township,
            "view": active_view,
        },
        "view_links": view_links,
        "form_action": "/union/report",
        "state_filterable": True,
        "all_districts": all_districts,
        "error": error,
    })


@router.get("/union/report/export")
async def union_report_export(
    request: Request,
    state: str = Query(""),
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = str(user.get("role") or "").strip().lower()
    if role != "union":
        raise HTTPException(
            403,
            "This report page is for union users only.",
        )

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        states = _get_all_states(cursor)
        selected_state = _resolve_state_report_state(states, state)
        if not selected_state:
            raise HTTPException(400, "State is required.")

        districts = _get_state_report_districts(cursor, selected_state)
        selected_district = _resolve_state_district(districts, district)
        if not selected_district:
            raise HTTPException(400, "ခရိုင်များ မရှိပါ။")

        townships = _get_state_report_townships(
            cursor, selected_state, selected_district,
        )
        selected_township = _resolve_state_township(
            townships, township, default_first=True,
        )
        if not selected_township:
            raise HTTPException(400, "မြို့နယ်များ မရှိပါ။")

        state_name = _get_state_report_place(cursor, selected_state)
        _, district_name, township_name = _get_township_report_place(
            cursor, selected_state, selected_district, selected_township,
        )
        villages = _query_township_village_report(
            cursor, selected_state, selected_district, selected_township,
            start_date, end_date,
        )
        output = build_township_report_workbook(
            villages, state_name, district_name, township_name,
            start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Union village report export error")
        raise HTTPException(
            500,
            "Unable to export union village report. Please try again later.",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_Union_Village_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/union/report/district/export")
async def union_report_district_export(
    request: Request,
    state: str = Query(""),
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = str(user.get("role") or "").strip().lower()
    if role != "union":
        raise HTTPException(
            403,
            "This report page is for union users only.",
        )

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        states = _get_all_states(cursor)
        selected_state = _resolve_state_report_state(states, state)
        if not selected_state:
            raise HTTPException(400, "State is required.")

        districts = _get_state_report_districts(cursor, selected_state)
        selected_district = _resolve_state_district(districts, district)
        if not selected_district:
            raise HTTPException(400, "ခရိုင်များ မရှိပါ။")

        townships = _get_state_report_townships(
            cursor, selected_state, selected_district,
        )
        selected_township = _resolve_state_township(townships, township)

        state_name = _get_state_report_place(cursor, selected_state)
        district_name = next(
            (str(row.get("districtName") or selected_district)
             for row in districts
             if str(row.get("districtID") or "") == selected_district),
            selected_district,
        )
        summary_rows = _query_district_township_summary(
            cursor, selected_state, selected_district, start_date, end_date,
            selected_township,
        )
        output = build_district_report_workbook(
            summary_rows, state_name, district_name,
            start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Union district summary export error")
        raise HTTPException(
            500,
            "Unable to export union district summary. Please try again later.",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_Union_District_Summary_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/union/report/state/export")
async def union_report_state_export(
    request: Request,
    state: str = Query(""),
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    role = str(user.get("role") or "").strip().lower()
    if role != "union":
        raise HTTPException(
            403,
            "This report page is for union users only.",
        )

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        states = _get_all_states(cursor)
        selected_state = _resolve_state_report_state(states, state)
        if not selected_state:
            raise HTTPException(400, "State is required.")

        districts = _get_state_report_districts(cursor, selected_state)
        selected_district = _resolve_state_district(districts, district) \
            if (district or "").strip() else ""

        townships = _get_state_report_townships(
            cursor, selected_state, selected_district,
        )
        selected_township = _resolve_state_township(townships, township)

        state_name = _get_state_report_place(cursor, selected_state)
        summary_rows = _query_state_township_summary(
            cursor, selected_state, selected_district, selected_township,
            start_date, end_date,
        )
        output = build_state_report_workbook(
            summary_rows, state_name, start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Union state summary export error")
        raise HTTPException(
            500,
            "Unable to export union state summary. Please try again later.",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_Union_State_Summary_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.get("/state/report/export")
async def state_report_export(
    request: Request,
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id = _state_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        districts = _get_state_report_districts(cursor, state_id)
        selected_district = _resolve_state_district(districts, district)
        if not selected_district:
            raise HTTPException(400, "ခရိုင်များ မရှိပါ။")

        townships = _get_state_report_townships(
            cursor, state_id, selected_district,
        )
        selected_township = _resolve_state_township(
            townships, township, default_first=True,
        )
        if not selected_township:
            raise HTTPException(400, "မြို့နယ်များ မရှိပါ။")

        state_name = _get_state_report_place(cursor, state_id)
        _, district_name, township_name = _get_township_report_place(
            cursor, state_id, selected_district, selected_township,
        )
        villages = _query_township_village_report(
            cursor, state_id, selected_district, selected_township,
            start_date, end_date,
        )
        output = build_township_report_workbook(
            villages, state_name, district_name, township_name,
            start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("State village report export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_State_Village_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/state/report/district/export")
async def state_report_district_export(
    request: Request,
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id = _state_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        districts = _get_state_report_districts(cursor, state_id)
        selected_district = _resolve_state_district(districts, district)
        if not selected_district:
            raise HTTPException(400, "ခရိုင်များ မရှိပါ။")

        townships = _get_state_report_townships(
            cursor, state_id, selected_district,
        )
        selected_township = _resolve_state_township(townships, township)

        state_name = _get_state_report_place(cursor, state_id)
        district_name = next(
            (str(row.get("districtName") or selected_district)
             for row in districts
             if str(row.get("districtID") or "") == selected_district),
            selected_district,
        )
        summary_rows = _query_district_township_summary(
            cursor, state_id, selected_district, start_date, end_date,
            selected_township,
        )
        output = build_district_report_workbook(
            summary_rows, state_name, district_name,
            start_date, end_date,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("State district summary export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_State_District_Summary_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/state/report/state/export")
async def state_report_state_export(
    request: Request,
    district: str = Query(""), township: str = Query(""),
    start_date: str = Query(""), end_date: str = Query(""),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    state_id = _state_report_scope(user)

    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        districts = _get_state_report_districts(cursor, state_id)
        selected_district = (district or "").strip()
        if selected_district and not any(
            str(row.get("districtID") or "") == selected_district
            for row in districts
        ):
            selected_district = ""

        townships = _get_state_report_townships(
            cursor, state_id, selected_district,
        )
        selected_township = _resolve_state_township(townships, township)

        state_name = _get_state_report_place(cursor, state_id)
        summary_rows = _query_state_township_summary(
            cursor, state_id, selected_district, selected_township,
            start_date, end_date,
        )
        output = build_state_report_workbook(
            summary_rows, state_name, start_date, end_date,
        )
    except Exception:
        logger.exception("State summary export error")
        raise HTTPException(
            500,
            "Excel ဖိုင် ထုတ်ယူရာတွင် အမှားဖြစ်ပေါ်ပါသည်။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။",
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    filename = "LBVD_State_Summary_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
