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


class StateReportTests(unittest.TestCase):
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
                "INSERT INTO state VALUES ('s', 'State One')"
            ))
            connection.execute(text(
                "INSERT INTO district VALUES "
                "('s', 'd1', 'District One'), "
                "('s', 'd2', 'District Two')"
            ))
            connection.execute(text(
                "INSERT INTO township VALUES "
                "('s', 'd1', 't1', 'Township One'), "
                "('s', 'd1', 't2', 'Township Two'), "
                "('s', 'd2', 't1', 'Township Three'), "
                "('s', 'd2', 't2', 'Township Four')"
            ))
            connection.execute(text(
                "INSERT INTO qv VALUES "
                "('s', 'd1', 't1', 'q1', 'QV One'), "
                "('s', 'd1', 't2', 'q2', 'QV Two'), "
                "('s', 'd2', 't1', 'q3', 'QV Three')"
            ))
            connection.execute(text(
                "INSERT INTO village VALUES "
                "('s', 'd1', 't1', 'q1', 'v1', 'Village One'), "
                "('s', 'd1', 't1', 'q1', 'v2', 'Village Two'), "
                "('s', 'd1', 't2', 'q2', 'v3', 'Village Three'), "
                "('s', 'd2', 't1', 'q3', 'v4', 'Village Four'), "
                "('s', 'd1', 't1', 'q1', 'v5', 'Village Without Records')"
            ))
            connection.execute(text(
                "INSERT INTO personcv VALUES "
                "('p1', 's', 'd1', 't1', 'q1', 'v1', '2026-11-02', 1), "
                "('p2', 's', 'd1', 't1', 'q1', 'v1', '2026-11-03', 1), "
                "('p3', 's', 'd1', 't1', 'q1', 'v1', '2026-11-02', 0), "
                "('p4', 's', 'd1', 't2', 'q2', 'v3', '2026-11-02', 1), "
                "('p5', 's', 'd2', 't1', 'q3', 'v4', '2026-11-02', 1), "
                "('p6', 's', 'd1', 't1', 'q1', 'v2', '2026-12-01', 1)"
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

    def sign_in(self, role="state"):
        data = base64.b64encode(json.dumps({
            "user": {
                "id": 1,
                "role": role,
                "stateID": "s",
                "districtID": "d1",
                "townshipID": "t1",
            },
        }).encode())
        self.client.cookies.set(
            "test-session",
            TimestampSigner("test-key").sign(data).decode(),
        )

    def test_page_has_three_versions_and_state_scope(self):
        self.sign_in()
        village_page = self.client.get(
            "/state/report?view=village&district=d1&township=t1"
        )
        self.assertEqual(village_page.status_code, 200)
        self.assertIn("stateReportFilter", village_page.text)
        self.assertIn("District One", village_page.text)
        self.assertIn("Township One", village_page.text)
        self.assertIn("Village One", village_page.text)
        self.assertNotIn("Village Without Records", village_page.text)

        district_page = self.client.get(
            "/state/report?view=district&district=d1"
        )
        self.assertEqual(district_page.status_code, 200)
        self.assertIn("summary-report-table", district_page.text)
        self.assertIn(
            '<td class="village-name">Township One</td>', district_page.text,
        )
        self.assertIn(
            '<td class="village-name">Township Two</td>', district_page.text,
        )
        self.assertNotIn(
            '<td class="village-name">Township Three</td>', district_page.text,
        )

        state_page = self.client.get("/state/report?view=state")
        self.assertEqual(state_page.status_code, 200)
        self.assertIn("state-summary-table", state_page.text)
        self.assertIn("District One", state_page.text)
        self.assertIn("District Two", state_page.text)
        self.assertIn("Township Four", state_page.text)
        self.assertIn("ခရိုင်နှင့် မြို့နယ်အလိုက် အနှစ်ချုပ်", state_page.text)
        self.assertNotIn("ခရိုင်များမှ အပတ်စဉ်ပေးပို့ရမည့် အစီရင်ခံစာပုံစံ", state_page.text)

    def test_state_summary_filters_by_district(self):
        self.sign_in()
        response = self.client.get("/state/report?view=state&district=d1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<td class="township-name">Township One</td>', response.text,
        )
        self.assertIn(
            '<td class="township-name">Township Two</td>', response.text,
        )
        self.assertNotIn(
            '<td class="township-name">Township Three</td>', response.text,
        )
        self.assertNotIn(
            '<td class="township-name">Township Four</td>', response.text,
        )

    def test_township_options_are_scoped_to_selected_district(self):
        self.sign_in()
        response = self.client.get(
            "/state/report?view=state&district=d2&township=t1"
        )
        self.assertEqual(response.status_code, 200)
        township_select = re.search(
            r'<select[^>]*id="stateReportTownship".*?</select>',
            response.text,
            re.S,
        )
        self.assertIsNotNone(township_select)
        select_html = township_select.group(0)
        self.assertIn("Township Three", select_html)
        self.assertNotIn("Township One", select_html)
        selected_option = re.search(
            r'<option value="t1"[^>]*selected[^>]*>\s*([^<]+)',
            select_html,
            re.S,
        )
        self.assertIsNotNone(selected_option)
        self.assertEqual(selected_option.group(1).strip(), "Township Three")

    def test_township_filter_is_disabled_for_all_districts(self):
        self.sign_in()
        response = self.client.get("/state/report?view=state")
        self.assertEqual(response.status_code, 200)
        township_select = re.search(
            r'<select[^>]*id="stateReportTownship"[^>]*>',
            response.text,
            re.S,
        )
        self.assertIsNotNone(township_select)
        self.assertIn("disabled", township_select.group(0))
        self.assertIn(
            '<td class="township-name">Township One</td>', response.text,
        )
        self.assertIn(
            '<td class="township-name">Township Three</td>', response.text,
        )

    def test_district_change_defaults_to_township_in_that_district(self):
        self.sign_in()
        response = self.client.get("/state/report?view=district&district=d2")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<td class="village-name">Township Three</td>', response.text,
        )
        self.assertIn(
            '<td class="village-name">Township Four</td>', response.text,
        )
        self.assertNotIn(
            '<td class="village-name">Township One</td>', response.text,
        )

    def test_village_export_uses_state_district_and_township(self):
        self.sign_in()
        response = self.client.get(
            "/state/report/export?district=d1&township=t1"
            "&start_date=2026-11-02&end_date=2026-11-02"
        )
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["B8"].value, "Village One")
        self.assertEqual(sheet["C8"].value, "-")
        self.assertEqual(sheet["D8"].value, 1)

    def test_district_summary_export_can_filter_to_one_township(self):
        self.sign_in()
        response = self.client.get(
            "/state/report/district/export?district=d1&township=t2"
        )
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["A1"].value, "နောက်ဆက်တွဲ(ဃ)")
        self.assertEqual(
            [sheet.cell(8, column).value for column in range(1, 6)],
            [1, "Township Two", 1, 1, 1],
        )
        self.assertIsNone(sheet.cell(9, 1).value)

    def test_state_summary_export_matches_the_six_column_form(self):
        self.sign_in()
        response = self.client.get(
            "/state/report/state/export"
            "?start_date=2026-11-01&end_date=2026-11-05"
        )
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertIsNone(sheet.freeze_panes)
        self.assertEqual(sheet.sheet_view.selection[0].activeCell, "A1")
        self.assertEqual(sheet["A1"].value, "နောက်ဆက်တွဲ(င)")
        self.assertEqual(sheet["B6"].value, "ခရိုင်")
        self.assertEqual(sheet["C6"].value, "မြို့နယ်")
        self.assertEqual(sheet["D6"].value, "ကောက်ယူသော")
        self.assertEqual(sheet["D7"].value, "ရပ်ကွက်\nစုစုပေါင်း")
        self.assertEqual(sheet["E7"].value, "ကျေးရွာ\nစုစုပေါင်း")
        self.assertEqual(sheet["F6"].value, "အိမ်ထောင်စု")
        self.assertEqual(sheet["F7"].value, "စုစုပေါင်း")
        self.assertEqual(
            [sheet.cell(8, column).value for column in range(1, 7)],
            [1, "District One", "Township One", 1, 1, 2],
        )
        self.assertEqual(
            [sheet.cell(9, column).value for column in range(1, 7)],
            [2, "District One", "Township Two", 1, 1, 1],
        )
        self.assertEqual(
            [sheet.cell(10, column).value for column in range(1, 7)],
            [3, "District Two", "Township Four", 0, 0, 0],
        )
        self.assertEqual(
            [sheet.cell(11, column).value for column in range(1, 7)],
            [4, "District Two", "Township Three", 1, 1, 1],
        )
        values = [
            cell.value
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertNotIn(
            "ခရိုင်များမှ အပတ်စဉ်ပေးပို့ရမည့် အစီရင်ခံစာပုံစံ",
            values,
        )

    def test_state_guard_for_anonymous_and_other_roles(self):
        anonymous = self.client.get("/state/report", follow_redirects=False)
        self.assertEqual(anonymous.status_code, 303)
        self.assertEqual(anonymous.headers["location"], "/")

        self.sign_in("district")
        self.assertEqual(self.client.get("/state/report").status_code, 403)
        self.assertEqual(
            self.client.get("/state/report/state/export").status_code,
            403,
        )

        self.sign_in("township")
        self.assertEqual(self.client.get("/state/report").status_code, 403)


if __name__ == "__main__":
    unittest.main()
