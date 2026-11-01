import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse


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