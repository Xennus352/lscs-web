import base64
import json
import re
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.database import SQLAlchemyConnection
from app.routers.reports import router


class UnionReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        schemas = {
            "personcv": (
                "formID stateID districtID townshipID QVID WardName "
                "interviewDate status"
            ),
            "state": "stateID stateName",
            "district": "stateID districtID districtName",
            "township": "stateID districtID townshipID townshipName",
            "qv": "stateID districtID townshipID QVID QVName",
            "village": "stateID districtID townshipID QVID villageID villageName",
        }
        with self.engine.begin() as connection:
            for table, columns in schemas.items():
                connection.execute(text(
                    f"CREATE TABLE {table} ("
                    + ",".join(f"{column} TEXT" for column in columns.split())
                    + ")"
                ))
            connection.execute(text(
                "INSERT INTO state VALUES "
                "('s1', 'Alpha State'), ('s2', 'Beta State')"
            ))
            connection.execute(text(
                "INSERT INTO district VALUES "
                "('s1', 'd1', 'Alpha District'), "
                "('s1', 'd2', 'Alpha Second District'), "
                "('s2', 'd3', 'Beta District')"
            ))
            connection.execute(text(
                "INSERT INTO township VALUES "
                "('s1', 'd1', 't1', 'Alpha Township'), "
                "('s1', 'd2', 't2', 'Alpha Second Township'), "
                "('s2', 'd3', 't3', 'Beta Township'), "
                "('s2', 'd3', 't4', 'Beta Empty Township')"
            ))
            connection.execute(text(
                "INSERT INTO qv VALUES "
                "('s1', 'd1', 't1', 'q1', 'Alpha QV'), "
                "('s1', 'd2', 't2', 'q2', 'Alpha Second QV'), "
                "('s2', 'd3', 't3', 'q3', 'Beta QV')"
            ))
            connection.execute(text(
                "INSERT INTO village VALUES "
                "('s1', 'd1', 't1', 'q1', 'v1', 'Alpha Village'), "
                "('s1', 'd2', 't2', 'q2', 'v2', 'Alpha Second Village'), "
                "('s2', 'd3', 't3', 'q3', 'v3', 'Beta Village')"
            ))
            connection.execute(text(
                "INSERT INTO personcv VALUES "
                "('p1', 's1', 'd1', 't1', 'q1', 'v1', '2026-11-02', 1), "
                "('p2', 's1', 'd1', 't1', 'q1', 'v1', '2026-11-03', 1), "
                "('p3', 's1', 'd1', 't1', 'q1', 'v1', '2026-11-02', 0), "
                "('p4', 's1', 'd2', 't2', 'q2', 'v2', '2026-11-02', 1), "
                "('p5', 's2', 'd3', 't3', 'q3', 'v3', '2026-11-02', 1)"
            ))

        app = FastAPI()
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-key",
            session_cookie="test-session",
        )
        app.include_router(router)
        self.client = TestClient(app)
        self.database_patch = patch(
            "app.routers.reports.get_db_connection",
            side_effect=lambda: SQLAlchemyConnection(self.engine.connect()),
        )
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.client.close()
        self.engine.dispose()

    def sign_in(self, role="union"):
        data = base64.b64encode(json.dumps({
            "user": {
                "id": 1,
                "role": role,
                "stateID": "",
                "districtID": "",
                "townshipID": "",
            },
        }).encode())
        self.client.cookies.set(
            "test-session",
            TimestampSigner("test-key").sign(data).decode(),
        )

    def test_page_requires_union_role(self):
        anonymous = self.client.get("/union/report", follow_redirects=False)
        self.assertEqual(anonymous.status_code, 303)
        self.assertEqual(anonymous.headers["location"], "/")

        for role in ("state", "district", "township"):
            self.sign_in(role)
            self.assertEqual(
                self.client.get("/union/report").status_code, 403,
            )
            self.assertEqual(
                self.client.get("/union/report/export").status_code, 403,
            )

    def test_page_defaults_to_first_state_and_offers_state_select(self):
        self.sign_in()
        response = self.client.get("/union/report")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="stateReportState"', response.text)
        self.assertIn('name="state"', response.text)

        state_select = re.search(
            r'<select[^>]*id="stateReportState".*?</select>',
            response.text,
            re.S,
        )
        self.assertIsNotNone(state_select)
        select_html = state_select.group(0)
        self.assertIn("Alpha State", select_html)
        self.assertIn("Beta State", select_html)
        self.assertNotIn("အားလုံး", select_html)
        self.assertIn('value="s1"', select_html)
        self.assertIn("selected", select_html)

        self.assertIn("Alpha Village", response.text)
        self.assertNotIn("Beta Village", response.text)

    def test_village_view_scopes_to_selected_state(self):
        self.sign_in()
        response = self.client.get(
            "/union/report?view=village&state=s2&district=d3&township=t3"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Beta State", response.text)
        self.assertIn("Beta Village", response.text)
        self.assertNotIn("Alpha Village", response.text)
        self.assertNotIn("Alpha Second Village", response.text)

    def test_district_view_scopes_to_selected_state(self):
        self.sign_in()
        response = self.client.get(
            "/union/report?view=district&state=s1&district=d1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<td class="village-name">Alpha Township</td>', response.text,
        )
        self.assertNotIn(
            '<td class="village-name">Alpha Second Township</td>',
            response.text,
        )
        self.assertNotIn(
            '<td class="village-name">Beta Township</td>', response.text,
        )

    def test_state_view_scopes_to_selected_state(self):
        self.sign_in()
        response = self.client.get("/union/report?view=state&state=s2")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<td class="township-name">Beta Township</td>', response.text,
        )
        self.assertIn(
            '<td class="township-name">Beta Empty Township</td>',
            response.text,
        )
        self.assertNotIn(
            '<td class="township-name">Alpha Township</td>', response.text,
        )
        self.assertNotIn(
            '<td class="township-name">Alpha Second Township</td>',
            response.text,
        )

    def test_district_view_ignores_district_from_another_state(self):
        self.sign_in()
        response = self.client.get(
            "/union/report?view=district&state=s2&district=d1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<td class="village-name">Beta Township</td>', response.text,
        )
        self.assertIn(
            '<td class="village-name">Beta Empty Township</td>',
            response.text,
        )
        self.assertNotIn(
            '<td class="village-name">Alpha Township</td>', response.text,
        )

    def test_village_export_is_scoped_and_named_for_union(self):
        self.sign_in()
        response = self.client.get(
            "/union/report/export?state=s1&district=d1&township=t1"
            "&start_date=2026-11-02&end_date=2026-11-02"
        )
        self.assertEqual(response.status_code, 200)
        disposition = response.headers["content-disposition"]
        self.assertTrue(disposition.startswith(
            'attachment; filename="LBVD_Union_Village_Report_'
        ))
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["B8"].value, "Alpha Village")
        self.assertEqual(sheet["C8"].value, "-")
        self.assertEqual(sheet["D8"].value, 1)

    def test_district_export_is_scoped_and_named_for_union(self):
        self.sign_in()
        response = self.client.get(
            "/union/report/district/export?state=s1&district=d1"
        )
        self.assertEqual(response.status_code, 200)
        disposition = response.headers["content-disposition"]
        self.assertTrue(disposition.startswith(
            'attachment; filename="LBVD_Union_District_Summary_'
        ))
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["A1"].value, "နောက်ဆက်တွဲ(ဃ)")
        self.assertEqual(
            [sheet.cell(8, column).value for column in range(1, 6)],
            [1, "Alpha Township", 1, 1, 2],
        )
        self.assertIsNone(sheet.cell(9, 1).value)

    def test_state_export_is_scoped_and_named_for_union(self):
        self.sign_in()
        response = self.client.get("/union/report/state/export?state=s2")
        self.assertEqual(response.status_code, 200)
        disposition = response.headers["content-disposition"]
        self.assertTrue(disposition.startswith(
            'attachment; filename="LBVD_Union_State_Summary_'
        ))
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["A1"].value, "နောက်ဆက်တွဲ(င)")
        self.assertEqual(
            [sheet.cell(8, column).value for column in range(1, 7)],
            [1, "Beta District", "Beta Empty Township", 0, 0, 0],
        )
        self.assertEqual(
            [sheet.cell(9, column).value for column in range(1, 7)],
            [2, "Beta District", "Beta Township", 1, 1, 1],
        )
        values = [
            cell.value
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertNotIn("Alpha District", values)
        self.assertNotIn("Alpha Township", values)

    def test_export_redirects_anonymous_users(self):
        response = self.client.get(
            "/union/report/export", follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")


if __name__ == "__main__":
    unittest.main()
