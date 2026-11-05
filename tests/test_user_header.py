import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.database import SQLAlchemyConnection
from app.lookups import get_user_header_info


class UserHeaderInfoTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE district ("
                "stateID TEXT, districtID TEXT, districtName TEXT)"
            ))
            connection.execute(text(
                "CREATE TABLE township ("
                "stateID TEXT, districtID TEXT, townshipID TEXT, townshipName TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO district VALUES "
                "('s07', 'd02', 'Taungoo District')"
            ))
            connection.execute(text(
                "INSERT INTO township VALUES "
                "('s07', 'd02', 't01', 'Taungoo Township')"
            ))

        self.database_patch = patch(
            "app.lookups.get_db_connection",
            side_effect=lambda: SQLAlchemyConnection(self.engine.connect()),
        )
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.engine.dispose()

    def test_union_shows_rank_only(self):
        info = get_user_header_info({"role": "union"})
        self.assertEqual(info["rank_label"], "ပြည်ထောင်စုအဆင့်အသုံးပြုသူ")
        self.assertEqual(info["icon"], "bi-globe2")
        self.assertEqual(info["location_line"], "")

    def test_state_shows_rank_only(self):
        info = get_user_header_info({"role": "state", "stateID": "s07"})
        self.assertEqual(info["rank_label"], "တိုင်း/ပြည်နယ်အဆင့်အသုံးပြုသူ")
        self.assertEqual(info["icon"], "bi-map")
        self.assertEqual(info["location_line"], "")

    def test_district_shows_district_name(self):
        info = get_user_header_info({
            "role": "district",
            "stateID": "s07",
            "districtID": "d02",
        })
        self.assertEqual(info["rank_label"], "ခရိုင်အဆင့်အသုံးပြုသူ")
        self.assertEqual(info["icon"], "bi-geo-alt")
        self.assertEqual(info["location_line"], "Taungoo District")

    def test_township_shows_district_and_township(self):
        info = get_user_header_info({
            "role": "township",
            "stateID": "s07",
            "districtID": "d02",
            "townshipID": "t01",
        })
        self.assertEqual(info["rank_label"], "မြို့နယ်အဆင့်အသုံးပြုသူ")
        self.assertEqual(info["icon"], "bi-pin-map")
        self.assertEqual(
            info["location_line"], "Taungoo District၊Taungoo Township",
        )

    def test_other_roles_have_no_rank_label(self):
        info = get_user_header_info({"role": "admin"})
        self.assertEqual(info["rank_label"], "")
        self.assertEqual(info["icon"], "")
        self.assertEqual(info["location_line"], "")

    def test_missing_user_is_safe(self):
        self.assertEqual(
            get_user_header_info(None),
            {"role": "", "rank_label": "", "icon": "", "location_line": ""},
        )


if __name__ == "__main__":
    unittest.main()
