import base64
import json
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.database import SQLAlchemyConnection
from app.routers.villages import router


def _workbook_bytes(rows, sheets=1):
    wb = Workbook()
    ws = wb.active
    ws.title = "Villages"
    for row in rows:
        ws.append(row)
    for index in range(1, sheets):
        wb.create_sheet(f"Extra{index}").append(["villageName"])
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


class TemporaryVillageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE state (stateID TEXT, stateName TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE district ("
                "stateID TEXT, districtID TEXT, districtName TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE township ("
                "stateID TEXT, districtID TEXT, townshipID TEXT, townshipName TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE qv ("
                "stateID TEXT, districtID TEXT, townshipID TEXT, "
                "QVID TEXT, QVName TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE village ("
                "stateID TEXT, districtID TEXT, townshipID TEXT, "
                "QVID TEXT, villageID TEXT, villageName TEXT)"
            ))

            connection.execute(text(
                "INSERT INTO state VALUES ('s1', 'State One'), ('s2', 'State Two')"
            ))
            connection.execute(text(
                "INSERT INTO district VALUES "
                "('s1', 'd1', 'District One'), "
                "('s1', 'd2', 'District Two'), "
                "('s2', 'd9', 'Other District')"
            ))
            connection.execute(text(
                "INSERT INTO township VALUES "
                "('s1', 'd1', 't1', 'Township One'), "
                "('s1', 'd1', 't2', 'Township Two'), "
                "('s1', 'd2', 't1', 'Township Three'), "
                "('s2', 'd9', 't9', 'Other Township')"
            ))
            connection.execute(text(
                "INSERT INTO qv VALUES "
                "('s1', 'd1', 't1', 'q1', 'QV One'), "
                "('s1', 'd1', 't1', 'q2', 'QV Two'), "
                "('s1', 'd1', 't2', 'q3', 'QV Three'), "
                "('s1', 'd2', 't1', 'q4', 'QV Four'), "
                "('s2', 'd9', 't9', 'q9', 'Other QV')"
            ))
            connection.execute(text(
                "INSERT INTO village VALUES "
                "('s1', 'd1', 't1', 'q1', 'v001', 'Existing Village')"
            ))

        app = FastAPI()
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-key",
            session_cookie="test-session",
        )
        app.include_router(router)
        self.client = TestClient(app)

        self.id_counter = 1

        def fake_next_village_id(cursor, state_id, district_id, township_id, qv_id):
            self.id_counter += 1
            return f"v{self.id_counter:03d}"

        self.database_patch = patch(
            "app.routers.villages.get_db_connection",
            side_effect=lambda: SQLAlchemyConnection(self.engine.connect()),
        )
        self.database_patch.start()
        self.id_patch = patch(
            "app.routers.villages._next_village_id",
            side_effect=fake_next_village_id,
        )
        self.id_patch.start()

    def tearDown(self):
        self.id_patch.stop()
        self.database_patch.stop()
        self.client.close()
        self.engine.dispose()

    def sign_in(self, role="township", state="s1", district="d1", township="t1"):
        data = base64.b64encode(json.dumps({
            "user": {
                "id": 1,
                "role": role,
                "stateID": state,
                "districtID": district,
                "townshipID": township,
            },
        }).encode())
        self.client.cookies.set(
            "test-session",
            TimestampSigner("test-key").sign(data).decode(),
        )

    def village_rows(self):
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT stateID, districtID, townshipID, QVID, villageID, villageName "
                "FROM village ORDER BY districtID, townshipID, villageID"
            )).fetchall()
        return [tuple(row) for row in rows]

    # ------------------------------------------------------------------
    # Page / access control
    # ------------------------------------------------------------------
    def test_page_is_township_only_and_renders_location_selectors(self):
        self.sign_in()
        response = self.client.get("/township/temporary-village")
        self.assertEqual(response.status_code, 200)
        self.assertIn("District One", response.text)
        self.assertIn("Township One", response.text)
        self.assertIn("Existing Village", response.text)
        self.assertIn('id="filterDistrict"', response.text)
        self.assertIn('id="filterTownship"', response.text)
        self.assertIn('id="addDistrict"', response.text)
        self.assertIn('id="importDistrict"', response.text)

        self.client.cookies.clear()
        self.sign_in(role="state")
        self.assertEqual(
            self.client.get("/township/temporary-village").status_code,
            403,
        )

        self.client.cookies.clear()
        response = self.client.get(
            "/township/temporary-village", follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)

    def test_page_works_without_account_district_and_township(self):
        self.sign_in(district=None, township=None)
        response = self.client.get("/township/temporary-village")
        self.assertEqual(response.status_code, 200)
        self.assertIn("District One", response.text)
        self.assertIn("Township One", response.text)

    def test_page_uses_requested_district_and_township(self):
        self.sign_in()
        response = self.client.get(
            "/township/temporary-village?district=d2&township=t1"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("District Two", response.text)
        self.assertIn("Township Three", response.text)
        self.assertIn("QV Four", response.text)
        self.assertNotIn("Existing Village", response.text)

    def test_page_rejects_location_outside_account_state(self):
        self.sign_in()
        response = self.client.get(
            "/township/temporary-village?district=d9&township=t9"
        )
        self.assertEqual(response.status_code, 200)
        # The page falls back to the account location for unknown districts.
        self.assertIn("District One", response.text)
        self.assertNotIn("Other District", response.text)

    # ------------------------------------------------------------------
    # Options API
    # ------------------------------------------------------------------
    def test_options_api_returns_townships_and_qvs(self):
        self.sign_in()

        townships = self.client.get(
            "/api/township/temporary-villages/options?district=d1"
        )
        self.assertEqual(townships.status_code, 200)
        self.assertEqual(
            [item["townshipID"] for item in townships.json()["townships"]],
            ["t1", "t2"],
        )

        qvs = self.client.get(
            "/api/township/temporary-villages/options?district=d1&township=t1"
        )
        self.assertEqual(qvs.status_code, 200)
        self.assertEqual(
            [item["QVID"] for item in qvs.json()["qvs"]],
            ["q1", "q2"],
        )

    def test_options_api_rejects_location_outside_account_state(self):
        self.sign_in()
        response = self.client.get(
            "/api/township/temporary-villages/options?district=d9"
        )
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------------
    # List API
    # ------------------------------------------------------------------
    def test_list_api_filters_by_chosen_location(self):
        self.sign_in()

        all_rows = self.client.get(
            "/api/township/temporary-villages?district=d1&township=t1"
        )
        self.assertEqual(all_rows.status_code, 200)
        self.assertEqual(all_rows.json()["total"], 1)
        self.assertEqual(all_rows.json()["total_all"], 1)
        self.assertEqual(all_rows.json()["qv_count"], 2)
        self.assertEqual(
            all_rows.json()["villages"][0]["villageName"],
            "Existing Village",
        )

        empty = self.client.get(
            "/api/township/temporary-villages?district=d1&township=t1&qv=q2"
        )
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["total"], 0)
        self.assertEqual(empty.json()["total_all"], 1)

    def test_list_api_requires_district_and_township(self):
        self.sign_in()
        self.assertEqual(
            self.client.get(
                "/api/township/temporary-villages?district=d1"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/township/temporary-villages?district=d9&township=t9"
            ).status_code,
            400,
        )

    # ------------------------------------------------------------------
    # Create API
    # ------------------------------------------------------------------
    def test_create_uses_chosen_district_township_and_qv(self):
        self.sign_in()
        response = self.client.post(
            "/api/township/temporary-villages",
            data={
                "district": "d2",
                "township": "t1",
                "qv": "q4",
                "villageName": "New Village",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["village"]["districtID"], "d2"
        )
        self.assertEqual(response.json()["village"]["townshipID"], "t1")

        rows = self.village_rows()
        self.assertIn(
            ("s1", "d2", "t1", "q4", "v002", "New Village"),
            rows,
        )

    def test_create_rejects_location_outside_account_state(self):
        self.sign_in()
        response = self.client.post(
            "/api/township/temporary-villages",
            data={
                "district": "d9",
                "township": "t9",
                "qv": "q9",
                "villageName": "Other State Village",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.village_rows(), [
            ("s1", "d1", "t1", "q1", "v001", "Existing Village"),
        ])

    def test_create_rejects_duplicate_name_inside_same_qv(self):
        self.sign_in()
        response = self.client.post(
            "/api/township/temporary-villages",
            data={
                "district": "d1",
                "township": "t1",
                "qv": "q1",
                "villageName": "existing village",
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_create_allows_duplicate_name_in_different_qv(self):
        self.sign_in()
        response = self.client.post(
            "/api/township/temporary-villages",
            data={
                "district": "d1",
                "township": "t1",
                "qv": "q2",
                "villageName": "Existing Village",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

    # ------------------------------------------------------------------
    # Update / delete API
    # ------------------------------------------------------------------
    def test_update_and_delete_use_chosen_location(self):
        self.sign_in()

        update = self.client.put(
            "/api/township/temporary-villages/d1/t1/q1/v001",
            data={"qv": "q1", "villageName": "Updated Village"},
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertIn(
            ("s1", "d1", "t1", "q1", "v001", "Updated Village"),
            self.village_rows(),
        )

        delete = self.client.delete(
            "/api/township/temporary-villages/d1/t1/q1/v001"
        )
        self.assertEqual(delete.status_code, 200, delete.text)
        self.assertEqual(self.village_rows(), [])

    def test_update_rejects_location_outside_account_state(self):
        self.sign_in()
        response = self.client.put(
            "/api/township/temporary-villages/d9/t9/q9/v001",
            data={"qv": "q9", "villageName": "Hijacked"},
        )
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------------------------------
    # Excel template / import
    # ------------------------------------------------------------------
    def test_sample_excel_is_available_to_township_users(self):
        self.sign_in()
        response = self.client.get(
            "/api/township/temporary-villages/sample-excel"
        )
        self.assertEqual(response.status_code, 200)

        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["Villages"])
        rows = list(workbook.active.iter_rows(values_only=True))
        self.assertEqual(rows[0], ("No.", "villageName"))
        self.assertEqual(len(rows), 4)

    def test_sample_excel_guard(self):
        self.sign_in(role="union")
        self.assertEqual(
            self.client.get(
                "/api/township/temporary-villages/sample-excel"
            ).status_code,
            403,
        )

    def test_import_uses_chosen_location_and_reports_skipped_rows(self):
        self.sign_in()
        content = _workbook_bytes([
            ["No.", "villageName"],
            [1, "Imported One"],
            [2, ""],
            [3, "Imported Two"],
        ])

        response = self.client.post(
            "/api/township/temporary-villages/import-excel",
            data={"district": "d1", "township": "t2", "qv": "q3"},
            files={
                "file": (
                    "villages.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                ),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["inserted"], 2)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["district"], "d1")
        self.assertEqual(payload["township"], "t2")

        rows = self.village_rows()
        self.assertIn(("s1", "d1", "t2", "q3", "v002", "Imported One"), rows)
        self.assertIn(("s1", "d1", "t2", "q3", "v003", "Imported Two"), rows)

    def test_import_rejects_location_outside_account_state(self):
        self.sign_in()
        response = self.client.post(
            "/api/township/temporary-villages/import-excel",
            data={"district": "d9", "township": "t9", "qv": "q9"},
            files={
                "file": (
                    "villages.xlsx",
                    _workbook_bytes([["villageName"], ["Other"]]),
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
