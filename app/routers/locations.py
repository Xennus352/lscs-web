from fastapi import APIRouter, Request, Query, HTTPException

from app.database import get_db_connection
from app.dependencies import get_signed_in_user
from app.cache import get_cache, set_cache

router = APIRouter(tags=["locations"])

CACHE_TTL = 300


async def _cached_query(
    cache_key: str,
    sql: str,
    params: tuple = (),
):
    """Read cached data or fetch from MySQL."""
    cached = await get_cache(cache_key)

    if cached is not None:
        return cached

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute(sql, params)
        rows = cur.fetchall()

        await set_cache(cache_key, rows, ttl=CACHE_TTL)

        return rows
    finally:
        cur.close()
        conn.close()


@router.get("/api/locations")
async def get_locations(
    request: Request,
    state_id: str = Query(None),
    district_id: str = Query(None),
    township_id: str = Query(None),
    qv_id: str = Query(None),
):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")

    role = user["role"]

    if role not in (
        "admin", "union", "state", "district",
        "township", "enumerator", "staff"
    ):
        raise HTTPException(403, "ဤဒေတာကို ကြည့်ခွင့်မရှိပါ။")

    if role == "state":
        state_id = user.get("stateID")
        if not state_id:
            raise HTTPException(
                403,
                "အကောင့်တွင် တိုင်းဒေသကြီး/ပြည်နယ် မသတ်မှတ်ရသေးပါ။"
            )

    elif role == "district":
        state_id = user.get("stateID")
        district_id = user.get("districtID")

        if not state_id or not district_id:
            raise HTTPException(
                403,
                "အကောင့်တွင် သက်ဆိုင်ရာ ခရိုင် မသတ်မှတ်ရသေးပါ။"
            )

    elif role in ("township", "enumerator"):
        state_id = user.get("stateID")
        district_id = user.get("districtID")
        township_id = user.get("townshipID")

        if not all([state_id, district_id, township_id]):
            raise HTTPException(
                403,
                "အကောင့်တွင် သတ်မှတ်ထားသော Location မပြည့်စုံပါ။"
            )

    # Village records are dynamic. Do not cache them yet.
    if qv_id and state_id and district_id and township_id:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)

        try:
            cur.execute(
                "SELECT villageID, villageName FROM village "
                "WHERE stateID = %s AND districtID = %s "
                "AND townshipID = %s AND QVID = %s "
                "ORDER BY villageName",
                (state_id, district_id, township_id, qv_id),
            )
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    # Build cache keys using the effective user scope.
    scope = (
        f"{role}:{state_id or '*'}:"
        f"{district_id or '*'}:{township_id or '*'}"
    )

    if not state_id:
        return await _cached_query(
            f"locations:states:{scope}",
            "SELECT DISTINCT stateID, stateName "
            "FROM state ORDER BY stateName",
        )

    if not district_id:
        return await _cached_query(
            f"locations:districts:{scope}",
            "SELECT DISTINCT districtID, districtName "
            "FROM district WHERE stateID = %s "
            "ORDER BY districtName",
            (state_id,),
        )

    if not township_id:
        return await _cached_query(
            f"locations:townships:{scope}",
            "SELECT DISTINCT townshipID, townshipName "
            "FROM township WHERE stateID = %s "
            "AND districtID = %s ORDER BY townshipName",
            (state_id, district_id),
        )

    return await _cached_query(
        f"locations:qvs:{scope}",
        "SELECT DISTINCT QVID, QVName FROM qv "
        "WHERE stateID = %s AND districtID = %s "
        "AND townshipID = %s ORDER BY QVName",
        (state_id, district_id, township_id),
    )


@router.get("/fetchStates")
async def fetch_states():
    rows = await _cached_query(
        "locations:fetch:states",
        "SELECT stateID, stateName FROM state ORDER BY stateName",
    )
    return {"states": rows}


@router.get("/fetchDistricts/{stateID}")
async def fetch_districts(stateID: str):
    rows = await _cached_query(
        f"locations:fetch:districts:{stateID}",
        "SELECT districtID, districtName FROM district "
        "WHERE stateID = %s ORDER BY districtName",
        (stateID,),
    )
    return {"districts": rows}


@router.get("/fetchTownship/{districtID}/{stateID}")
async def fetch_townships(stateID: str, districtID: str):
    rows = await _cached_query(
        f"locations:fetch:townships:{stateID}:{districtID}",
        "SELECT townshipID, townshipName FROM township "
        "WHERE stateID = %s AND districtID = %s "
        "ORDER BY townshipName",
        (stateID, districtID),
    )
    return {"townships": rows}


@router.get("/fetchVillageTract/{townshipID}/{districtID}/{stateID}")
async def fetch_village_tracts(
    townshipID: str,
    districtID: str,
    stateID: str,
):
    rows = await _cached_query(
        f"locations:fetch:villagetracts:{stateID}:{districtID}:{townshipID}",
        "SELECT QVID AS id, QVName AS name FROM qv "
        "WHERE stateID = %s AND districtID = %s "
        "AND townshipID = %s ORDER BY QVName",
        (stateID, districtID, townshipID),
    )
    return {"villages": rows}


@router.get("/fetchQV/{stateID}/{townshipID}/{districtID}")
async def get_QVs(stateID: str, townshipID: str, districtID: str):
    rows = await _cached_query(
        f"locations:fetch:qvs:{stateID}:{districtID}:{townshipID}",
        "SELECT QVID AS qvID, QVName AS qvName FROM qv "
        "WHERE stateID = %s AND districtID = %s "
        "AND townshipID = %s ORDER BY QVName",
        (stateID, districtID, townshipID),
    )
    return {"qvs": rows}


@router.get("/sendStateValue/{stateID}")
async def getStateID(stateID: str, request: Request):
    request.session["stateID"] = {"stateID": stateID}
    return {"message": "store stateID"}


@router.get("/fetchlargeAniSpecies/{largeAniID}")
async def get_largeAniSpecies(largeAniID: str):
    rows = await _cached_query(
        f"locations:species:large:{largeAniID}",
        "SELECT speciesID, speciesName FROM largespecies "
        "WHERE animalID = %s ORDER BY speciesID",
        (largeAniID,),
    )
    return {"largeSpecies": rows}


@router.get("/fetchsmallAniSpecies/{youngAniID}")
async def get_youngAniSpecies(youngAniID: str):
    rows = await _cached_query(
        f"locations:species:young:{youngAniID}",
        "SELECT speciesID, speciesName FROM youngspecies "
        "WHERE animalID = %s ORDER BY speciesID",
        (youngAniID,),
    )
    return {"smallSpecies": rows}


@router.get("/fetchLiveStockSpecies/{liveStockID}")
async def get_liveStockSpecies(liveStockID: str):
    rows = await _cached_query(
        f"locations:species:livestock:{liveStockID}",
        "SELECT speciesID, speciesName FROM livestockspecies "
        "WHERE animalID = %s ORDER BY speciesID",
        (liveStockID,),
    )
    return {"liveStockSpecies": rows}
