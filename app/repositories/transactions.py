"""Small helpers for classifying transient MySQL errors.

MariaDB/MySQL use SQLSTATE / error numbers that survive the SQLAlchemy
compatibility layer, so string matching on ``exc.orig`` is stable enough for
the handful of cases the application retries.
"""
from __future__ import annotations

_RETRYABLE_MARKERS = (
    "1213",              # deadlock
    "1205",              # lock wait timeout
    "deadlock",
    "lock wait timeout",
    "try restarting transaction",
)


def _error_text(exc) -> str:
    origin = getattr(exc, "orig", None) or exc
    return str(origin).lower()


def is_retryable_error(exc) -> bool:
    text = _error_text(exc)
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def is_duplicate_record_uuid_error(exc) -> bool:
    text = _error_text(exc)
    duplicate = "duplicate" in text or "1062" in text
    return duplicate and "record_uuid" in text


def is_duplicate_form_id_error(exc) -> bool:
    text = _error_text(exc)
    duplicate = "duplicate" in text or "1062" in text
    return duplicate and ("formid" in text or "primary" in text)
