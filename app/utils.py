import csv
import io
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.config import CSV_ENCODING

logger = logging.getLogger("lbvd")




import hashlib
import os
from pathlib import Path
from packaging.version import Version, InvalidVersion

from .constants import APK_DIR, APK_VERSION_RE


def parse_apk_version(filename: str) -> Version | None:
    m = APK_VERSION_RE.search(filename)
    if not m:
        return None
    try:
        return Version(m.group("ver"))
    except InvalidVersion:
        return None


def find_latest_apk() -> tuple[str, Version, os.stat_result] | None:
    """Latest APK ကို version နဲ့ ရှာပြန်ပေးတယ်။ မရှိရင် None."""
    best = None
    try:
        with os.scandir(APK_DIR) as it:
            for entry in it:
                if not entry.is_file() or not entry.name.endswith(".apk"):
                    continue
                ver = parse_apk_version(entry.name)
                if ver is None:
                    continue
                st = entry.stat()
                if best is None or ver > best[1]:
                    best = (entry.name, ver, st)
    except OSError:
        return None
    return best


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

# ============================================================
# 📅 DATE FILTER HELPERS
# ============================================================
def _resolve_date_range(start_date: Optional[str] = None,
                        end_date: Optional[str] = None):
    start_date = (start_date or "").strip()
    end_date = (end_date or "").strip()

    if not start_date and not end_date:
        return None, None
    if start_date and not end_date:
        return start_date, start_date
    if end_date and not start_date:
        return end_date, end_date
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


# ============================================================
# 🆔 FORM ID GENERATOR
# ============================================================
def generate_formatted_id(counter_value: int) -> str:
    """Formats an integer into a zero-padded string identifier."""
    current_year = datetime.now().year
    return f"FORM-{current_year}-{counter_value:05d}"


# ============================================================
# 📥 CSV EXPORT HELPER
# ============================================================
def make_csv_response(rows: list, headers: list, filename: str) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel UTF-8
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    content = buf.getvalue()
    buf.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = f"{filename}_{stamp}.csv"
    return StreamingResponse(
        iter([content.encode(CSV_ENCODING)]),
        media_type=f"text/csv; charset={CSV_ENCODING}",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}"; '
                f"filename*=UTF-8''{safe_name}"
            ),
            "Cache-Control": "no-store",
        },
    )
    # ============================================================
# 🆔 NEXT ID GENERATORS (used by system_admin animal creation)
# ============================================================
def next_numeric_id(db, table, id_col, prefix, width):
    """
    Returns next ID like 'la01', 'la02', ... for the given table & prefix.
    db: SQLAlchemy Session
    """
    try:
        rows = db.execute(
            text(f"SELECT {id_col} FROM {table} WHERE {id_col} LIKE :p"),
            {"p": f"{prefix}%"},
        ).fetchall()
    except Exception as e:
        logger.error("next_numeric_id lookup failed (%s.%s): %s", table, id_col, e)
        raise

    max_n = 0
    for row in rows:
        s = str(row[0] or "")
        if not s.startswith(prefix):
            continue
        digits = re.sub(r"\D", "", s[len(prefix):])
        if not digits:
            continue
        try:
            n = int(digits)
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{prefix}{(max_n + 1):0{width}d}"


def next_species_id(db, species_table, species_prefix, animal_id,
                    animal_prefix, width=4):
    """
    Returns next species ID like 'laS0001', 'laS0002', ...
    """
    try:
        rows = db.execute(
            text(f"SELECT speciesID FROM {species_table} "
                 "WHERE speciesID LIKE :p"),
            {"p": f"{species_prefix}%"},
        ).fetchall()
    except Exception as e:
        logger.error("next_species_id lookup failed (%s): %s", species_table, e)
        raise

    max_n = 0
    for row in rows:
        s = str(row[0] or "")
        if not s.startswith(species_prefix):
            continue
        digits = re.sub(r"\D", "", s[len(species_prefix):])
        if not digits:
            continue
        try:
            n = int(digits)
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{species_prefix}{(max_n + 1):0{width}d}"