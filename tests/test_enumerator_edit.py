import base64
import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.database import SQLAlchemyConnection
from app.routers.enumerator import router


class _SqliteCursor:
    """Strip MySQL row locks so the same routes run against SQLite tests."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        return self._cursor.execute(sql.replace(" FOR UPDATE", ""), params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        return self._cursor.close()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid


class _SqliteConnection(SQLAlchemyConnection):
    def cursor(self, dictionary=False):
        return _SqliteCursor(super().cursor(dictionary=dictionary))


class EnumeratorEditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE personcv ("
                "formID TEXT, userId TEXT, name TEXT, age TEXT, "
                "householdNo TEXT, interviewDate TEXT, status TEXT, "
                "WardName TEXT, stateID TEXT, districtID TEXT, townshipID TEXT, "
                "QVID TEXT, version INTEGER NOT NULL DEFAULT 1)"
            ))
            connection.execute(text(
                "CREATE TABLE collecteddata ("
                "formID TEXT, animalTypeID TEXT, animalID TEXT, speciesID TEXT, "
                "ageID TEXT, genderID TEXT, dataCount TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO personcv "
                "(formID, userId, name, age, householdNo, interviewDate, status, "
                "WardName, stateID, districtID, townshipID, QVID) VALUES "
                "('p1', '1', 'Old Name', '30', 'H1', '2026-11-02', '1', "
                "'v1', 's1', 'd1', 't1', 'q1'), "
                "('p2', '2', 'Other User', '40', 'H9', '2026-11-02', '1', "
                "'v9', 's1', 'd1', 't1', 'q1')"
            ))
            connection.execute(text(
                "INSERT INTO collecteddata VALUES "
                "('p1', 'at1', 'a1', 's1', 'age1', 'g1', '2')"
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
            "app.routers.enumerator.get_db_connection",
            side_effect=lambda: _SqliteConnection(self.engine.connect()),
        )
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.client.close()
        self.engine.dispose()

    def sign_in(self, role="enumerator", user_id=1):
        data = base64.b64encode(json.dumps({
            "user": {
                "id": user_id,
                "role": role,
                "stateID": "s1",
                "districtID": "d1",
                "townshipID": "t1",
            },
        }).encode())
        self.client.cookies.set(
            "test-session",
            TimestampSigner("test-key").sign(data).decode(),
        )

    def test_edit_page_has_save_but_no_form_delete(self):
        self.sign_in()
        response = self.client.get("/enumerator/edit-form")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="saveBtn"', response.text)
        self.assertIn('id="formFields"', response.text)
        self.assertNotIn("delete", response.text.lower())

        # The whole-form DELETE route must no longer exist.
        self.assertEqual(
            self.client.delete("/enumerator/api/forms/p1").status_code,
            405,
        )

    def test_enumerator_can_still_update_and_save_the_form(self):
        self.sign_in()
        response = self.client.put(
            "/enumerator/api/forms/p1",
            json={
                "personcv": {
                    "name": "New Name",
                    "age": "31",
                    "householdNo": "H2",
                },
                "collecteddata": [{
                    "animalTypeID": "at1",
                    "animalID": "a2",
                    "speciesID": "s2",
                    "ageID": "age2",
                    "genderID": "g2",
                    "dataCount": "3",
                }],
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["formID"], "p1")
        self.assertEqual(payload["animalRecordsSaved"], 1)

        with self.engine.connect() as connection:
            person = connection.execute(text(
                "SELECT name, age, householdNo FROM personcv WHERE formID = 'p1'"
            )).fetchone()
            self.assertEqual(tuple(person), ("New Name", "31", "H2"))

            animals = connection.execute(text(
                "SELECT animalID, dataCount FROM collecteddata WHERE formID = 'p1'"
            )).fetchall()
            self.assertEqual([tuple(row) for row in animals], [("a2", "3")])

            # Updating a form must never remove the form itself.
            total_forms = connection.execute(text(
                "SELECT COUNT(*) FROM personcv WHERE formID = 'p1'"
            )).scalar()
            self.assertEqual(total_forms, 1)

    def test_enumerator_cannot_update_another_users_form(self):
        self.sign_in()
        response = self.client.put(
            "/enumerator/api/forms/p2",
            json={"personcv": {"name": "Trying Another"}, "collecteddata": []},
        )
        self.assertEqual(response.status_code, 404)
        with self.engine.connect() as connection:
            name = connection.execute(text(
                "SELECT name FROM personcv WHERE formID = 'p2'"
            )).scalar()
            self.assertEqual(name, "Other User")

    def test_stale_version_is_rejected(self):
        self.sign_in()
        response = self.client.put(
            "/enumerator/api/forms/p1",
            json={
                "personcv": {"name": "Should Not Save"},
                "collecteddata": [],
                "version": 99,
            },
        )
        self.assertEqual(response.status_code, 409)
        with self.engine.connect() as connection:
            name = connection.execute(text(
                "SELECT name FROM personcv WHERE formID = 'p1'"
            )).scalar()
            self.assertEqual(name, "Old Name")

    def test_current_version_is_accepted_and_incremented(self):
        self.sign_in()
        response = self.client.put(
            "/enumerator/api/forms/p1",
            json={
                "personcv": {"name": "Versioned"},
                "collecteddata": [],
                "version": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)
        with self.engine.connect() as connection:
            version = connection.execute(text(
                "SELECT version FROM personcv WHERE formID = 'p1'"
            )).scalar()
            self.assertEqual(version, 2)

    def test_non_enumerator_cannot_use_edit_routes(self):
        self.sign_in("township")
        self.assertEqual(
            self.client.get("/enumerator/edit-form").status_code, 403,
        )
        self.assertEqual(
            self.client.put(
                "/enumerator/api/forms/p1",
                json={"personcv": {"name": "Blocked"}, "collecteddata": []},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
