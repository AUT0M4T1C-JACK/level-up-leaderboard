import logging
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class StartupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        cwd = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, cwd)

        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

        bot = patch("level_up_leaderboard.bot.LevelUpBot")
        self.bot = bot.start()
        self.addCleanup(bot.stop)
        storage = patch("level_up_leaderboard.storage.Storage")
        self.storage = storage.start()
        self.addCleanup(storage.stop)

    def test_loads_token_and_data_file_from_dotenv(self):
        (self.directory / ".env").write_text(
            "DISCORD_TOKEN=dotenv-test-value\nDATA_FILE=birthdays.json\n",
            encoding="utf-8",
        )

        runpy.run_module("level_up_leaderboard", run_name="__main__")

        self.storage.assert_called_once_with("birthdays.json")
        self.bot.assert_called_once_with(self.storage.return_value)
        self.bot.return_value.run.assert_called_once_with(
            "dotenv-test-value", log_level=logging.INFO
        )

    def test_exported_environment_takes_precedence(self):
        (self.directory / ".env").write_text(
            "DISCORD_TOKEN=dotenv-test-value\nDATA_FILE=dotenv.json\n",
            encoding="utf-8",
        )
        os.environ.update(DISCORD_TOKEN="exported-test-value", DATA_FILE="exported.json")

        runpy.run_module("level_up_leaderboard", run_name="__main__")

        self.storage.assert_called_once_with("exported.json")
        self.bot.return_value.run.assert_called_once_with(
            "exported-test-value", log_level=logging.INFO
        )

    def test_exported_token_works_without_dotenv(self):
        os.environ["DISCORD_TOKEN"] = "exported-test-value"

        runpy.run_module("level_up_leaderboard", run_name="__main__")

        self.storage.assert_called_once_with("data.json")
        self.bot.return_value.run.assert_called_once_with(
            "exported-test-value", log_level=logging.INFO
        )

    def test_missing_token_preserves_error(self):
        with self.assertRaisesRegex(SystemExit, "Set the DISCORD_TOKEN environment variable"):
            runpy.run_module("level_up_leaderboard", run_name="__main__")

        self.storage.assert_not_called()
        self.bot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
