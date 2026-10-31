import csv
import hashlib
import io
import logging
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi.responses import StreamingResponse
from packaging.version import InvalidVersion, Version
from sqlalchemy import text

from app.config import CSV_ENCODING
from app.constants import APK_DIR

logger = logging.getLogger("lbvd")

_VERSION_IN_NAME = re.compile(r"(\d+(?:\.\d+)*)")


# ============================================================
# 📱 APK UPDATE HELPERS
# ============================================================
def version_from_filename(filename: str) -> Version | None:
    """Extract a version from an APK filename (e.g. ``lbvd-1.2.3.apk``).

    The last version-like token wins so date-prefixed names such as
    ``lbvd-2026-01-1.2.3.apk`` still resolve to ``1.2.3``.
    """
    matches = _VERSION_IN_NAME.findall(Path(filename).stem)
    for raw in reversed(matches):
        try:
            return Version(raw)
        except InvalidVersion:
            continue
    return None


def find_latest_apk(directory: Path | None = None):
    """Return ``(filename, Version, os.stat_result)`` for the newest APK.

    Returns ``None`` when the folder is missing/empty or no APK has a
    parseable version in its filename.
    """
    directory = Path(directory or APK_DIR)
    try:
        candidates = [
            entry for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".apk"
        ]
    except OSError:
        return None

    latest = None
    for path in candidates:
        version = version_from_filename(path.name)
        if version is None:
            logger.warning("Skipping APK without a version in its name: %s", path.name)
            continue
        try:
            stat = path.stat()
        except OSError as exc:
            logger.warning("Cannot stat APK %s: %s", path.name, exc)
            continue

        if latest is None:
            latest = (path.name, version, stat)
            continue

        _, latest_version, latest_stat = latest
        if (version, stat.st_mtime) > (latest_version, latest_stat.st_mtime):
            latest = (path.name, version, stat)

    return latest


@lru_cache(maxsize=16)
def _sha256_cached(path: str, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file without loading it all in memory.

    Results are cached per path/size/mtime, so repeated update checks do not
    re-hash a large APK.
    """
    p = Path(path)
    stat = p.stat()
    return _sha256_cached(str(p.resolve()), stat.st_size, stat.st_mtime_ns)


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
            text(f"SELECT `{id_col}` FROM `{table}` WHERE `{id_col}` LIKE :p"),
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
            text(f"SELECT `speciesID` FROM `{species_table}` "
                 "WHERE `speciesID` LIKE :p"),
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