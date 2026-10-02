import tempfile
import unittest
from datetime import date
from pathlib import Path

from level_up_leaderboard.levels import (
    MAX_LEADERBOARD_CHARS,
    birthday_in_year,
    is_birthday,
    level_on,
    render_leaderboard,
)
from level_up_leaderboard.storage import DEFAULT_REACTION_EMOJI, Storage


class LevelTests(unittest.TestCase):
    def test_level_increments_on_birthday(self):
        self.assertEqual(level_on(15, 6, 2000, date(2026, 6, 14)), 25)
        self.assertEqual(level_on(15, 6, 2000, date(2026, 6, 15)), 26)
        self.assertEqual(level_on(15, 6, 2000, date(2026, 12, 31)), 26)

    def test_leap_day_birthday_celebrated_feb_28_in_common_years(self):
        self.assertEqual(birthday_in_year(2, 29, 2027), date(2027, 2, 28))
        self.assertEqual(birthday_in_year(2, 29, 2028), date(2028, 2, 29))
        self.assertTrue(is_birthday(2, 29, date(2027, 2, 28)))
        self.assertFalse(is_birthday(2, 29, date(2028, 2, 28)))
        self.assertEqual(level_on(29, 2, 2000, date(2027, 2, 27)), 26)
        self.assertEqual(level_on(29, 2, 2000, date(2027, 2, 28)), 27)

    def test_is_birthday(self):
        self.assertTrue(is_birthday(10, 2, date(2026, 10, 2)))
        self.assertFalse(is_birthday(10, 2, date(2026, 10, 3)))


class LeaderboardTests(unittest.TestCase):
    def test_ranked_by_level_then_oldest(self):
        board = render_leaderboard(
            [
                ("young", 20, date(2006, 1, 1)),
                ("old", 40, date(1986, 1, 1)),
                ("twin-b", 30, date(1996, 5, 2)),
                ("twin-a", 30, date(1996, 3, 1)),
            ]
        )
        lines = board.splitlines()
        self.assertTrue(board.startswith("```") and board.endswith("```"))
        ranked = [line for line in lines if "Lv" in line]
        self.assertEqual([line.split()[1] for line in ranked], ["old", "twin-a", "twin-b", "young"])
        self.assertTrue(ranked[0].endswith("|" + "#" * 40))
        self.assertTrue(ranked[3].endswith("|" + "#" * 20))

    def test_bar_has_one_hashtag_per_level(self):
        board = render_leaderboard([("user", 22, date(2004, 1, 1))])
        ranked = [line for line in board.splitlines() if "Lv" in line]
        self.assertTrue(ranked[0].endswith("|" + "#" * 22))

    def test_empty_board(self):
        self.assertIn("No one has registered yet", render_leaderboard([]))

    def test_names_are_sanitised_and_truncated(self):
        board = render_leaderboard([("```a very long name indeed", 5, date(2021, 1, 1))])
        self.assertEqual(board.count("```"), 2)
        self.assertIn("'''a very long ~", board)

    def test_long_boards_fit_in_a_discord_message(self):
        board = render_leaderboard([(f"user{i}", i % 90, date(1930 + i % 90, 1, 1)) for i in range(200)])
        self.assertLessEqual(len(board), MAX_LEADERBOARD_CHARS)
        self.assertIn("more", board.splitlines()[-2])


class StorageTests(unittest.TestCase):
    def test_round_trip_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            storage = Storage(path)
            settings = storage.guild(123)
            self.assertEqual(settings["reaction_emoji"], DEFAULT_REACTION_EMOJI)
            settings["birthdays"]["42"] = {"day": 1, "month": 2, "year": 2000, "name": "Al", "last_announced": None}
            storage.save()

            reloaded = Storage(path)
            self.assertEqual(reloaded.guild(123)["birthdays"]["42"]["name"], "Al")


if __name__ == "__main__":
    unittest.main()
