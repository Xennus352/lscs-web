from fastapi import APIRouter, Request, Query, HTTPException
from app.database import get_db_connection
from app.dependencies import get_signed_in_user

router = APIRouter(tags=["locations"])


@router.get("/api/locations")
async def get_locations(
    request: Request,
    state_id: str = Query(None),
    district_id: str = Query(None),
    township_id: str = Query(None),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township", "enumerator", "staff"):
        raise HTTPException(403, "ဤဒေတာကို ကြည့်ခွင့်မရှိပါ။")

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        if role == "state":
            state_id = user.get("stateID")
            if not state_id: raise HTTPException(403, "အကောင့်တွင် တိုင်းဒေသကြီး/ပြည်နယ် မသတ်မှတ်ရသေးပါ။")
        elif role == "district":
            state_id, district_id = user.get("stateID"), user.get("districtID")
            if not state_id or not district_id:
                raise HTTPException(403, "အကောင့်တွင် သက်ဆိုင်ရာ ခရိုင် မသတ်မှတ်ရသေးပါ။")
        elif role in ("township", "enumerator"):
            state_id    = user.get("stateID")
            district_id = user.get("districtID")
            township_id = user.get("townshipID")
            if not all([state_id, district_id, township_id]):
                raise HTTPException(403, "အကောင့်တွင် သတ်မှတ်ထားသော Location မပြည့်စုံပါ။")

        if not state_id:
            cur.execute("SELECT DISTINCT stateID, stateName FROM state ORDER BY stateName")
            return cur.fetchall()
        if not district_id:
            cur.execute("SELECT DISTINCT districtID, districtName FROM district "
                        "WHERE stateID = %s ORDER BY districtName", (state_id,))
            return cur.fetchall()
        if not township_id:
            cur.execute("SELECT DISTINCT townshipID, townshipName FROM township "
                        "WHERE stateID = %s AND districtID = %s ORDER BY townshipName",
                        (state_id, district_id))
            return cur.fetchall()
        cur.execute("SELECT DISTINCT QVID, QVName FROM qv "
                    "WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName",
                    (state_id, district_id, township_id))
        return cur.fetchall()
    finally:
        cur.close(); conn.close()


@router.get("/fetchStates")
async def fetch_states():
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT stateID, stateName FROM state ORDER BY stateName")
        return {"states": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchDistricts/{stateID}")
async def fetch_districts(stateID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT districtID, districtName FROM district "
                    "WHERE stateID = %s ORDER BY districtName", (stateID,))
        return {"districts": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchTownship/{districtID}/{stateID}")
async def fetch_townships(stateID: str, districtID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT townshipID, townshipName FROM township "
                    "WHERE stateID = %s AND districtID = %s ORDER BY townshipName",
                    (stateID, districtID))
        return {"townships": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchVillageTract/{townshipID}/{districtID}/{stateID}")
async def fetch_village_tracts(townshipID: str, districtID: str, stateID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT QVID AS id, QVName AS name FROM qv "
                    "WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName",
                    (stateID, districtID, townshipID))
        return {"villages": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchQV/{stateID}/{townshipID}/{districtID}")
async def get_QVs(stateID: str, townshipID: str, districtID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT QVID AS qvID, QVName AS qvName FROM qv "
                    "WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName",
                    (stateID, districtID, townshipID))
        return {"qvs": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/sendStateValue/{stateID}")
async def getStateID(stateID: str, request: Request):
    request.session["stateID"] = {"stateID": stateID}
    return {"message": "store stateID"}


@router.get("/fetchlargeAniSpecies/{largeAniID}")
async def get_largeAniSpecies(largeAniID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT speciesID, speciesName FROM largespecies "
                    "WHERE animalID = %s ORDER BY speciesID", (largeAniID,))
        return {"largeSpecies": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchsmallAniSpecies/{youngAniID}")
async def get_youngAniSpecies(youngAniID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT speciesID, speciesName FROM youngspecies "
                    "WHERE animalID = %s ORDER BY speciesID", (youngAniID,))
        return {"smallSpecies": cur.fetchall()}
    finally:
        cur.close(); conn.close()


@router.get("/fetchLiveStockSpecies/{liveStockID}")
async def get_liveStockSpecies(liveStockID: str):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT speciesID, speciesName FROM livestockspecies "
                    "WHERE animalID = %s ORDER BY speciesID", (liveStockID,))
        return {"liveStockSpecies": cur.fetchall()}
    finally:
        cur.close(); conn.close()