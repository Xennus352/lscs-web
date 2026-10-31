import logging

from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db_connection

logger = logging.getLogger("lbvd")


# ============================================================
# 🔍 STATE / ANIMAL LOOKUPS
# ============================================================
def _get_user_state_name(user):
    if not user or not user.get("stateID"):
        return ""
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT stateName FROM state WHERE stateID = %s", (user["stateID"],))
            r = cur.fetchone()
            return r["stateName"] if r else ""
        finally:
            cur.close(); conn.close()
    except Exception as e:
        logger.warning(f"State name lookup failed: {e}")
        return ""


def _get_all_states():
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT stateID, stateName FROM state ORDER BY stateName")
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"_get_all_states: {e}")
        return []


def _get_all_large_animals():
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT animalID, animalName FROM largeanimals "
                        "WHERE animalTypeID = 'atID01' ORDER BY animalID")
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"_get_all_large_animals: {e}")
        return []


def _get_all_small_animals():
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT animalID, animalName FROM younganimals "
                        "WHERE animalTypeID = 'atID02' ORDER BY animalID")
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"_get_all_small_animals: {e}")
        return []


def _get_all_livestock_animals():
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT animalID, animalName FROM livestock "
                        "WHERE animalTypeID = 'atID03' ORDER BY animalID")
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"_get_all_livestock_animals: {e}")
        return []


def _get_all_breeding_animals():
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT animalID, animalName FROM breedingstock "
                        "WHERE animalTypeID = %s ORDER BY animalID", ("atID04",))
            return cur.fetchall()
        finally:
            cur.close(); conn.close()
    except Exception as exc:
        logger.warning(f"Breeding animal lookup failed: {exc}")
        return []


# ============================================================
# 🔍 GENERIC LOOKUP TABLES
# ============================================================
LOOKUP_TABLES = {
    "animalTypes": "animaltype",
    "largeAnimals": "largeanimals",
    "youngAnimals": "younganimals",
    "liveStock": "livestock",
    "breedingstock": "breedingstock",
    "species": "livestockspecies",
    "ages": "agetype",
    "genders": "gender",
}
LOOKUP_ID_CANDIDATES = {
    "animalTypes": ["atID", "animalTypeID", "animalTypeId"],
    "largeAnimals": ["laID", "animalID", "largeAnimalID"],
    "youngAnimals": ["yaID", "animalID", "youngAnimalID"],
    "liveStock": ["lsID", "animalID", "liveStockID"],
    "breedingstock": ["bsID", "animalID", "breedingstockID"],
    "species": ["speciesID", "spID", "lsSpeciesID"],
    "ages": ["ageID"],
    "genders": ["genderID", "gID"],
}
LOOKUP_NAME_CANDIDATES = {
    "animalTypes": ["animalTypeName", "atName", "animalType"],
    "largeAnimals": ["largeAnimalName", "laName", "animalName"],
    "youngAnimals": ["youngAnimalName", "yaName", "animalName"],
    "liveStock": ["liveStockName", "lsName", "animalName"],
    "breedingstock": ["breedingstockName", "bsName", "animalName"],
    "species": ["speciesName", "spName", "liveStockSpecies"],
    "ages": ["ageName", "ageTypeName", "ageType"],
    "genders": ["genderName", "gName", "gender"],
}


def get_lookup_rows(cursor, lookup_key):
    if lookup_key not in LOOKUP_TABLES:
        raise ValueError("Invalid lookup key")

    table_name = LOOKUP_TABLES[lookup_key]
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    columns = [row["Field"] for row in cursor.fetchall()]
    if not columns:
        return []

    id_column = next(
        (col for col in LOOKUP_ID_CANDIDATES[lookup_key] if col in columns), None,
    )
    name_column = next(
        (col for col in LOOKUP_NAME_CANDIDATES[lookup_key] if col in columns), None,
    )
    if id_column is None:
        id_column = next(
            (col for col in columns
             if col.lower().endswith("id") and col.lower() not in ("formid", "userid")),
            None,
        )
    if name_column is None:
        name_column = next(
            (col for col in columns
             if "name" in col.lower() or col.lower() in ("animaltype", "agetype", "gender")),
            None,
        )
    if id_column is None or name_column is None:
        raise ValueError(f"Lookup schema မကိုက်ညီပါ: {table_name}; columns={columns}")

    cursor.execute(f"SELECT * FROM `{table_name}` ORDER BY `{id_column}`")
    result = []
    for row in cursor.fetchall():
        item = {"id": row.get(id_column), "name": row.get(name_column)}
        item.update(row)
        result.append(item)
    return result


def load_animal_lookup(cursor):
    lookup = {"animalTypes": get_lookup_rows(cursor, "animalTypes"), "animals": []}

    animal_sources = [
        ("atID01", "largeAnimals"),
        ("atID02", "youngAnimals"),
        ("atID03", "liveStock"),
        ("atID04", "breedingstock"),
    ]
    for type_id, source_key in animal_sources:
        for item in get_lookup_rows(cursor, source_key):
            animal = dict(item)
            animal["animalTypeID"] = type_id
            lookup["animals"].append(animal)

    lookup["species"] = []
    for table, type_id in [
        ("largespecies", "atID01"),
        ("youngspecies", "atID02"),
        ("livestockspecies", "atID03"),
    ]:
        try:
            cursor.execute(f"SELECT * FROM {table}")
            for row in cursor.fetchall():
                lookup["species"].append({
                    "id": row.get("speciesID"),
                    "name": row.get("speciesName"),
                    "animalID": row.get("animalID"),
                    "animalTypeID": type_id,
                    **row,
                })
        except Exception as e:
            logger.warning(f"{table} lookup failed: {e}")

    lookup["ages"] = get_lookup_rows(cursor, "ages")
    lookup["genders"] = get_lookup_rows(cursor, "genders")
    return lookup