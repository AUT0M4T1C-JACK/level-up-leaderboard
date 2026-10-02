import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from level_up_leaderboard.bot import LevelUpBot
from level_up_leaderboard.storage import Storage

TODAY = date(2026, 10, 2)


class BotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = LevelUpBot(Storage(Path(self.tmp.name) / "data.json"))
        self.settings = self.bot.storage.guild(1)
        self.settings["birthdays"] = {
            "10": {"day": 2, "month": 10, "year": 2000, "name": "Birthday", "last_announced": None},
            "20": {"day": 3, "month": 10, "year": 1990, "name": "Tomorrow", "last_announced": None},
        }
        self.channel = MagicMock()
        self.channel.send = AsyncMock(return_value=MagicMock(id=999))
        self.guild = MagicMock(id=1)
        self.guild.get_channel.return_value = self.channel
        self.guild.get_member.return_value = None
        patcher = patch("level_up_leaderboard.bot.atlanta_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    async def run_birthday_check(self):
        with patch.object(LevelUpBot, "guilds", new=[self.guild]):
            await self.bot.birthday_check.coro(self.bot)

    async def test_levels_up_once_and_updates_leaderboard(self):
        self.settings["leaderboard_channel_id"] = 5

        await self.run_birthday_check()
        level_up, leaderboard = (call.args[0] for call in self.channel.send.call_args_list)
        self.assertIn("<@10>", level_up)
        self.assertIn("Level 26", level_up)
        self.assertNotIn("<@20>", level_up)
        self.assertIn("Birthday", leaderboard)
        self.assertEqual(self.settings["leaderboard_message_id"], 999)
        self.assertEqual(self.settings["birthdays"]["10"]["last_announced"], TODAY.isoformat())

        self.channel.send.reset_mock()
        await self.run_birthday_check()
        self.channel.send.assert_not_called()

    async def test_no_channel_configured_skips(self):
        await self.run_birthday_check()
        self.channel.send.assert_not_called()
        self.assertIsNone(self.settings["birthdays"]["10"]["last_announced"])

    async def test_existing_leaderboard_message_is_edited(self):
        self.settings["leaderboard_channel_id"] = 5
        self.settings["leaderboard_message_id"] = 777
        partial = MagicMock()
        partial.edit = AsyncMock()
        self.channel.get_partial_message.return_value = partial

        await self.bot.update_leaderboard(self.guild)
        self.channel.get_partial_message.assert_called_with(777)
        partial.edit.assert_awaited_once()
        self.channel.send.assert_not_called()

    async def test_deleted_leaderboard_message_is_reposted(self):
        self.settings["leaderboard_channel_id"] = 5
        self.settings["leaderboard_message_id"] = 777
        partial = MagicMock()
        partial.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "gone"))
        self.channel.get_partial_message.return_value = partial

        await self.bot.update_leaderboard(self.guild)
        self.channel.send.assert_awaited_once()
        self.assertEqual(self.settings["leaderboard_message_id"], 999)

    async def test_reacts_only_on_birthday(self):
        self.settings["reaction_emoji"] = "🆙"
        for author_id, should_react in ((10, True), (20, False), (30, False)):
            message = MagicMock()
            message.guild.id = 1
            message.author.id = author_id
            message.author.bot = False
            message.add_reaction = AsyncMock()
            await self.bot.on_message(message)
            if should_react:
                message.add_reaction.assert_awaited_once_with("🆙")
            else:
                message.add_reaction.assert_not_called()


if __name__ == "__main__":
    unittest.main()
