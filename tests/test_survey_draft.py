import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.services import survey_draft


def _request(session):
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/survey/part1",
        "headers": [],
        "session": session,
    })


class LegacyDraftMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_session_keys_are_migrated_once(self):
        session = {
            "formID": "FORM-2026-00001",
            "record_uuid": "11111111-2222-3333-4444-555555555555",
            "step1": {"name": "Draft", "age": "30"},
            "animals_data": {"largeAnimalsTable": [], "youngAnimalsTable": []},
            "unrelated": "keep me",
        }
        request = _request(session)

        # Force the session fallback path so no Redis server is needed.
        with patch.object(survey_draft, "_redis_available", return_value=False):
            draft = await survey_draft.load_draft(request)

        self.assertEqual(draft["formID"], "FORM-2026-00001")
        self.assertEqual(draft["step1"]["name"], "Draft")
        self.assertEqual(session["unrelated"], "keep me")
        # Legacy keys moved into the single fallback key.
        self.assertNotIn("step1", session)
        self.assertNotIn("formID", session)
        self.assertEqual(session[survey_draft.DRAFT_SESSION_KEY]["step1"]["name"], "Draft")

        # A second read returns the same draft without changing the session.
        with patch.object(survey_draft, "_redis_available", return_value=False):
            again = await survey_draft.load_draft(request)
        self.assertEqual(again, draft)

    async def test_leaves_unrelated_session_keys_when_no_draft_exists(self):
        session = {"user": {"id": 7}, "unrelated": "value"}
        request = _request(session)

        with patch.object(survey_draft, "_redis_available", return_value=False):
            draft = await survey_draft.load_draft(request)

        self.assertEqual(draft, {})
        self.assertEqual(session["unrelated"], "value")
        self.assertNotIn(survey_draft.DRAFT_SESSION_KEY, session)


if __name__ == "__main__":
    unittest.main()
