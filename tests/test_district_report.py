import base64
import json
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


class DistrictReportTests(unittest.TestCase):
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
                "INSERT INTO state VALUES ('s', 'State')"
            ))
            connection.execute(text(
                "INSERT INTO district VALUES ('s', 'd', 'District')"
            ))
            connection.execute(text(
                "INSERT INTO township VALUES "
                "('s', 'd', 't1', 'Township One'), "
                "('s', 'd', 't2', 'Township Two')"
            ))
            connection.execute(text(
                "INSERT INTO qv VALUES ('s', 'd', 't1', 'q1', 'QV One')"
            ))
            connection.execute(text(
                "INSERT INTO village VALUES "
                "('s', 'd', 't1', 'q1', 'v1', 'Village One')"
            ))
            connection.execute(text(
                "INSERT INTO personcv VALUES "
                "('p1', 's', 'd', 't1', 'q1', 'v1', '2026-11-02', 1), "
                "('p2', 's', 'd', 't1', 'q1', 'v1', '2026-11-03', 1), "
                "('p3', 's', 'd', 't1', 'q1', 'v1', '2026-11-02', 0), "
                "('p4', 's', 'd', 't2', 'q2', 'v2', '2026-11-02', 1)"
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

    def sign_in(self, role="district"):
        data = base64.b64encode(json.dumps({
            "user": {
                "id": 1,
                "role": role,
                "stateID": "s",
                "districtID": "d",
                "townshipID": "t1",
            },
        }).encode())
        self.client.cookies.set(
            "test-session",
            TimestampSigner("test-key").sign(data).decode(),
        )

    def test_page_shows_both_versions_and_respects_district_scope(self):
        self.sign_in()
        village_page = self.client.get(
            "/district/report?view=village&township=t1"
        )
        self.assertEqual(village_page.status_code, 200)
        self.assertIn("districtReportFilter", village_page.text)
        self.assertIn("Township One", village_page.text)

        summary_page = self.client.get("/district/report?view=summary")
        self.assertEqual(summary_page.status_code, 200)
        self.assertIn("summary-report-table", summary_page.text)
        self.assertIn("Township One", summary_page.text)
        self.assertIn("Township Two", summary_page.text)
        self.assertNotIn("official-table", summary_page.text)
        self.assertNotIn("ခရိုင်များမှ အပတ်စဉ်ပေးပို့ရမည့် အစီရင်ခံစာပုံစံ", summary_page.text)

    def test_village_export_uses_selected_township_and_date_range(self):
        self.sign_in()
        response = self.client.get(
            "/district/report/export?township=t1"
            "&start_date=2026-11-02&end_date=2026-11-02"
        )
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual(sheet["B8"].value, "Village One")
        self.assertEqual(sheet["C8"].value, "-")
        self.assertEqual(sheet["D8"].value, 1)

    def test_summary_export_matches_the_official_five_column_form(self):
        self.sign_in()
        response = self.client.get("/district/report/summary/export")
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertIsNone(sheet.freeze_panes)
        self.assertEqual(sheet.sheet_view.selection[0].activeCell, "A1")
        self.assertEqual(sheet["A1"].value, "နောက်ဆက်တွဲ(ဃ)")
        self.assertEqual(sheet["B7"].value, "မြို့နယ်")
        self.assertEqual(
            [sheet.cell(8, column).value for column in range(1, 6)],
            [1, "Township One", 1, 1, 2],
        )
        self.assertEqual(
            [sheet.cell(9, column).value for column in range(1, 6)],
            [2, "Township Two", 1, 1, 1],
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

    def test_district_guard_for_anonymous_and_other_roles(self):
        anonymous = self.client.get(
            "/district/report", follow_redirects=False
        )
        self.assertEqual(anonymous.status_code, 303)
        self.assertEqual(anonymous.headers["location"], "/")

        self.sign_in("township")
        self.assertEqual(self.client.get("/district/report").status_code, 403)
        self.assertEqual(
            self.client.get("/district/report/summary/export").status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
