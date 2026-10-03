import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from level_up_leaderboard.bot import BirthdayCommands, LevelUpBot, MONTHS
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

    async def test_set_birthday_accepts_numeric_and_named_months(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 30
        interaction.user.display_name = "New Birthday"
        interaction.response.send_message = AsyncMock()
        for month_number, month_name in enumerate(MONTHS, 1):
            for month in (str(month_number), f"{month_number:02}", month_name, f" {month_name.lower()} "):
                with self.subTest(month=month), patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock) as update:
                    await commands.set_birthday.callback(commands, interaction, day=10, month=month, year=2000)
                    birthday = self.settings["birthdays"]["30"]
                    self.assertEqual(birthday["month"], month_number)
                    self.assertEqual(birthday["day"], 10)
                    self.assertEqual(birthday["year"], 2000)
                    self.assertEqual(birthday["name"], "New Birthday")
                    self.assertIsNone(birthday["last_announced"])
                    self.assertEqual(Storage(self.bot.storage.path).guild(1)["birthdays"]["30"], birthday)
                    self.assertIn(f"{month_name} 10.", interaction.response.send_message.call_args.args[0])
                    self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])
                    update.assert_awaited_once_with(self.guild)

    async def test_set_birthday_rejects_invalid_months_and_dates(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 10
        interaction.response.send_message = AsyncMock()
        original = self.settings["birthdays"]["10"].copy()
        cases = [
            (10, month, 2000, "Enter a month name or a number from 1 to 12.")
            for month in ("0", "13", "-1", "1.5", "", "NotAMonth", "9" * 5000)
        ] + [
            (31, month, 2000, "April 31 isn't a real date in 2000.") for month in ("4", "April")
        ] + [
            (29, month, 2001, "February 29 isn't a real date in 2001.") for month in ("2", "February")
        ] + [
            (3, month, 2026, "You can't be born in the future!") for month in ("10", "October")
        ]
        for day, month, year, error in cases:
            with self.subTest(day=day, month=month, year=year), \
                    patch.object(self.bot.storage, "save") as save, \
                    patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock) as update:
                interaction.response.send_message.reset_mock()
                await commands.set_birthday.callback(commands, interaction, day=day, month=month, year=year)
                interaction.response.send_message.assert_awaited_once_with(error, ephemeral=True)
                self.assertEqual(self.settings["birthdays"]["10"], original)
                save.assert_not_called()
                update.assert_not_awaited()

    async def test_set_birthday_accepts_leap_day_and_today(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 30
        interaction.user.display_name = "New Birthday"
        interaction.response.send_message = AsyncMock()
        for day, month, year, announced in (
            (29, "2", 2000, None), (29, "February", 2000, None),
            (2, "10", 2026, TODAY.isoformat()), (2, "October", 2026, TODAY.isoformat()),
        ):
            with self.subTest(month=month), patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock):
                await commands.set_birthday.callback(commands, interaction, day=day, month=month, year=year)
                self.assertEqual(self.settings["birthdays"]["30"]["last_announced"], announced)

    async def test_remove_birthday_only_owner_can_remove_another_member(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 10
        interaction.user.name = "someone_else"
        interaction.response.send_message = AsyncMock()
        member = MagicMock(id=20, display_name="Tomorrow", mention="<@20>")

        with patch.object(self.bot.storage, "save") as save, \
                patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock) as update:
            await commands.remove_birthday.callback(commands, interaction, member)

        self.assertIn("20", self.settings["birthdays"])
        self.assertEqual(self.settings["birthdays"]["10"]["name"], "Birthday")
        save.assert_not_called()
        update.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "Only the leaderboard owner can remove someone else's birthday.", ephemeral=True
        )

    async def test_owner_can_remove_another_member_birthday(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 10
        interaction.user.name = "AUT0M4T1C_JACK"
        interaction.response.send_message = AsyncMock()
        member = MagicMock(id=20, display_name="Tomorrow", mention="<@20>")

        with patch.object(self.bot.storage, "save") as save, \
                patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock) as update:
            await commands.remove_birthday.callback(commands, interaction, member)

        self.assertNotIn("20", self.settings["birthdays"])
        self.assertIn("10", self.settings["birthdays"])
        save.assert_called_once()
        update.assert_awaited_once_with(self.guild)
        interaction.response.send_message.assert_awaited_once_with(
            "Removed <@20> from the leaderboard.", ephemeral=True
        )

    async def test_member_can_still_remove_own_birthday(self):
        commands = BirthdayCommands()
        interaction = MagicMock(client=self.bot, guild_id=1, guild=self.guild)
        interaction.user.id = 10
        interaction.user.name = "someone_else"
        interaction.response.send_message = AsyncMock()

        with patch.object(self.bot.storage, "save") as save, \
                patch.object(self.bot, "update_leaderboard", new_callable=AsyncMock) as update:
            await commands.remove_birthday.callback(commands, interaction)

        self.assertNotIn("10", self.settings["birthdays"])
        self.assertIn("20", self.settings["birthdays"])
        save.assert_called_once()
        update.assert_awaited_once_with(self.guild)
        interaction.response.send_message.assert_awaited_once_with(
            "Removed you from the leaderboard.", ephemeral=True
        )

    async def test_month_autocomplete_supports_names_and_numbers(self):
        commands = BirthdayCommands()
        for current, expected in (("", MONTHS), (" ja ", ["January"]), ("2", ["February"]), ("12", ["December"])):
            with self.subTest(current=current):
                choices = await commands.month_autocomplete(MagicMock(), current)
                self.assertEqual([choice.name for choice in choices], expected)
                self.assertEqual([choice.value for choice in choices], expected)
        month = next(parameter for parameter in commands.set_birthday.parameters if parameter.name == "month")
        self.assertEqual(month.type, discord.AppCommandOptionType.string)
        self.assertTrue(month.autocomplete)
        self.assertEqual(month.choices, [])


if __name__ == "__main__":
    unittest.main()
