import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.requests import Request

from app.routers import survey


class NonCollectionPart1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_status_zero_initializes_age_values_before_submit(self):
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/enumerator/part1",
            "headers": [],
            "session": {},
        })
        user = {
            "stateID": "s1",
            "districtID": "d1",
            "townshipID": "t1",
        }
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        submit = AsyncMock(return_value={"status": "success"})

        with patch.object(survey, "_guard_enumerator_web_route", return_value=user), \
                patch.object(survey, "get_db_connection", return_value=connection), \
                patch.object(survey, "_resolve_village_id", return_value="Village"), \
                patch.object(survey, "compat_submit_survey", submit):
            result = await survey.compat_process_step_1(
                request=request,
                formID="TEMP-FORM-ID-0001",
                districtID="d1",
                townshipID="t1",
                qvID="q1",
                wardName="Village",
                houseHoldNo="H1",
                interviewDate="2026-11-14",
                collection_status="0",
                db=MagicMock(),
            )

        self.assertEqual(result, {"status": "success"})
        self.assertEqual(request.session["step1"]["age"], "0")
        self.assertEqual(request.session["step1"]["headAge"], "0")
        submit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
