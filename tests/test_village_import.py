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


class VillageImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with self.engine.begin() as connection:
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
                "INSERT INTO qv VALUES ('s', 'd1', 't1', 'q1', 'QV One')"
            ))
            connection.execute(text(
                "INSERT INTO village VALUES "
                "('s', 'd1', 't1', 'q1', 'v001', 'Existing Village')"
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

    def sign_in(self, role="township"):
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

    def import_file(self, content, filename="villages.xlsx", qv="q1"):
        return self.client.post(
            "/api/township/villages/import-excel",
            data={"qv": qv},
            files={
                "file": (
                    filename,
                    content,
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                ),
            },
        )

    def village_names(self):
        with self.engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT stateID, districtID, townshipID, QVID, villageName "
                "FROM village ORDER BY villageID"
            )).fetchall()
        return [tuple(row) for row in rows]

    # ------------------------------------------------------------------
    # Sample workbook
    # ------------------------------------------------------------------
    def test_sample_excel_has_three_rows_and_required_headers(self):
        self.sign_in()
        response = self.client.get("/api/township/villages/sample-excel")

        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["Villages"])
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(rows[0], ("No.", "villageName"))
        self.assertEqual(len(rows), 4)
        self.assertEqual([row[0] for row in rows[1:]], [1, 2, 3])
        self.assertTrue(all(row[1] for row in rows[1:]))

    def test_sample_excel_guard(self):
        self.sign_in(role="state")
        self.assertEqual(
            self.client.get("/api/township/villages/sample-excel").status_code,
            403,
        )
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get("/api/township/villages/sample-excel").status_code,
            401,
        )

    # ------------------------------------------------------------------
    # Import success path
    # ------------------------------------------------------------------
    def test_import_inserts_rows_with_account_scope_and_skips_invalid(self):
        self.sign_in()
        content = _workbook_bytes([
            ["No.", "villageName"],
            [1, "New Village A"],
            [2, ""],
            [3, "existing village"],
            [4, "New Village B"],
        ])

        response = self.import_file(content)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["inserted"], 2)
        self.assertEqual(payload["skipped"], 2)
        # Duplicate names are compared case-insensitively.
        skipped_names = {item["villageName"] for item in payload["errors"]}
        self.assertIn("existing village", skipped_names)

        rows = self.village_names()
        self.assertEqual(rows[0], ("s", "d1", "t1", "q1", "Existing Village"))
        self.assertEqual(rows[1], ("s", "d1", "t1", "q1", "New Village A"))
        self.assertEqual(rows[2], ("s", "d1", "t1", "q1", "New Village B"))

    def test_import_accepts_village_name_only_and_detects_in_file_duplicates(self):
        self.sign_in()
        content = _workbook_bytes([
            ["villageName"],
            ["Only Column"],
            ["Only Column"],
        ])

        response = self.import_file(content)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["inserted"], 1)
        self.assertEqual(payload["skipped"], 1)

    # ------------------------------------------------------------------
    # Validation failures
    # ------------------------------------------------------------------
    def test_import_rejects_multiple_sheets(self):
        self.sign_in()
        response = self.import_file(_workbook_bytes(
            [["villageName"], ["Village"]], sheets=2,
        ))
        self.assertEqual(response.status_code, 400)
        self.assertIn("sheet", response.json()["detail"])

    def test_import_rejects_more_than_two_columns(self):
        self.sign_in()
        response = self.import_file(_workbook_bytes([
            ["No.", "villageName", "Extra"],
            [1, "Village", "x"],
        ]))
        self.assertEqual(response.status_code, 400)

    def test_import_requires_exact_village_name_column(self):
        self.sign_in()
        response = self.import_file(_workbook_bytes([
            ["No.", "village_name"],
            [1, "Village"],
        ]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("villageName", response.json()["detail"])

    def test_import_requires_no_as_the_first_column(self):
        self.sign_in()

        inverted = self.import_file(_workbook_bytes([
            ["villageName", "No."],
            ["Village", 1],
        ]))
        self.assertEqual(inverted.status_code, 400)
        self.assertIn("No.", inverted.json()["detail"])

        wrong_label = self.import_file(_workbook_bytes([
            ["Number", "villageName"],
            [1, "Village"],
        ]))
        self.assertEqual(wrong_label.status_code, 400)

    def test_import_requires_a_qv_and_an_xlsx_file(self):
        self.sign_in()

        missing_qv = self.import_file(
            _workbook_bytes([["villageName"], ["Village"]]), qv="",
        )
        self.assertEqual(missing_qv.status_code, 400)

        wrong_extension = self.import_file(
            _workbook_bytes([["villageName"], ["Village"]]),
            filename="villages.xls",
        )
        self.assertEqual(wrong_extension.status_code, 400)

    def test_import_rejects_unknown_qv(self):
        self.sign_in()
        response = self.import_file(
            _workbook_bytes([["villageName"], ["Village"]]), qv="nope",
        )
        self.assertEqual(response.status_code, 400)

    def test_import_guard_for_non_township_roles(self):
        self.sign_in(role="union")
        response = self.import_file(
            _workbook_bytes([["villageName"], ["Village"]]),
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
