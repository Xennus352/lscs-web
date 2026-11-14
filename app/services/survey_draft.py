"""Server-side storage for an in-progress survey form.

Previously every part of the wizard wrote its payload into
``request.session``. Starlette sessions are signed cookies, so a form with a
handful of animal rows produced a multi-kilobyte cookie and larger forms were
silently truncated by the browser or proxy (5 rows ≈ 5 KB, 20 rows ≈ 18 KB).

The cookie now only carries a small ``draft_id``. The draft itself lives in
Redis and expires automatically. If Redis is unavailable the code falls back
to the old session storage so surveys keep working, but the common path never
grows the cookie.
"""
from __future__ import annotations

import copy
import json
import logging
import time
import uuid

from redis.exceptions import RedisError

from app.config import SURVEY_DRAFT_TTL_SECONDS
from app.redis_client import redis_client

logger = logging.getLogger("lbvd.survey_draft")

DRAFT_ID_KEY = "draft_id"
DRAFT_SESSION_KEY = "survey_draft"
DRAFT_FIELDS = (
    "formID",
    "record_uuid",
    "step1",
    "animals_data",
    "livestock_data",
    "breeding_animals_data",
    "interviewer",
    "interviewerPhoneNo",
)

DRAFT_TTL_SECONDS = SURVEY_DRAFT_TTL_SECONDS
_REDIS_RETRY_AFTER = 30.0
_redis_down_until = 0.0


def _redis_available() -> bool:
    return time.monotonic() >= _redis_down_until


def _mark_redis_down() -> None:
    global _redis_down_until
    _redis_down_until = time.monotonic() + _REDIS_RETRY_AFTER


def _draft_id(request) -> str:
    draft_id = request.session.get(DRAFT_ID_KEY)
    if not draft_id:
        draft_id = str(uuid.uuid4())
        request.session[DRAFT_ID_KEY] = draft_id
    return draft_id


def redis_key(request) -> str:
    user = request.session.get("user") or {}
    user_id = user.get("id", "anon")
    return f"lbvd:survey_draft:{user_id}:{_draft_id(request)}"


def _session_fallback(request) -> dict:
    value = request.session.get(DRAFT_SESSION_KEY)
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _normalise(data) -> dict:
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in DRAFT_FIELDS if key in data}


async def load_draft(request) -> dict:
    """Return the current draft (empty dict when there is none).

    Drafts created before the Redis migration live in individual session keys
    (``step1``, ``animals_data``, ...). They are imported once on first read so
    a deploy does not wipe surveys that were already in progress.
    """
    if _redis_available():
        try:
            raw = await redis_client.get(redis_key(request))
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return _normalise(parsed)
        except (RedisError, json.JSONDecodeError):
            _mark_redis_down()
            logger.warning("Survey draft read failed; using session fallback", exc_info=True)

    fallback = _session_fallback(request)
    if fallback:
        return fallback

    legacy = _legacy_session_draft(request)
    if legacy:
        migrated = await save_draft(request, legacy)
        _pop_legacy_session_draft(request)
        logger.info("Migrated legacy session draft (keys: %s)", ", ".join(legacy))
        return migrated
    return {}


def _legacy_session_draft(request) -> dict:
    """Collect a draft stored by the pre-Redis wizard."""
    draft = {}
    for key in DRAFT_FIELDS:
        if key in request.session:
            draft[key] = copy.deepcopy(request.session[key])
    return _normalise(draft)


def _pop_legacy_session_draft(request) -> None:
    for key in DRAFT_FIELDS:
        request.session.pop(key, None)


async def save_draft(request, data: dict) -> dict:
    """Replace the draft with ``data`` and persist it."""
    cleaned = _normalise(data)

    if _redis_available():
        try:
            await redis_client.set(
                redis_key(request),
                json.dumps(cleaned, ensure_ascii=False, default=str),
                ex=DRAFT_TTL_SECONDS,
            )
            # Keep the cookie small once Redis has the authoritative copy.
            request.session.pop(DRAFT_SESSION_KEY, None)
            return cleaned
        except RedisError:
            _mark_redis_down()
            logger.warning("Survey draft write failed; using session fallback", exc_info=True)

    request.session[DRAFT_SESSION_KEY] = cleaned
    return cleaned


async def update_draft(request, **values) -> dict:
    """Merge ``values`` into the current draft."""
    draft = await load_draft(request)
    draft.update({key: value for key, value in values.items() if key in DRAFT_FIELDS})
    return await save_draft(request, draft)


async def clear_draft(request) -> None:
    """Drop the draft (successful submit, cancelled non-collection form)."""
    if _redis_available():
        try:
            await redis_client.delete(redis_key(request))
        except RedisError:
            _mark_redis_down()
            logger.warning("Survey draft delete failed", exc_info=True)
    request.session.pop(DRAFT_SESSION_KEY, None)
    request.session.pop(DRAFT_ID_KEY, None)
    _pop_legacy_session_draft(request)
