"""The Discord side of Level Up Leaderboard."""

import logging
from datetime import date

import discord
from discord import app_commands
from discord.ext import tasks

from .levels import atlanta_today, is_birthday, level_on, render_leaderboard
from .storage import Storage

log = logging.getLogger(__name__)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


class LevelUpBot(discord.Client):
    def __init__(self, storage: Storage):
        # Default intents are enough: we never read message content or the member list.
        super().__init__(intents=discord.Intents.default())
        self.storage = storage
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(BirthdayCommands())
        self.tree.add_command(SettingsCommands())

    async def setup_hook(self) -> None:
        await self.tree.sync()
        self.birthday_check.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        settings = self.storage.guild(message.guild.id)
        birthday = settings["birthdays"].get(str(message.author.id))
        if birthday is None or not is_birthday(birthday["month"], birthday["day"], atlanta_today()):
            return
        try:
            await message.add_reaction(settings["reaction_emoji"])
        except discord.HTTPException:
            log.warning("Couldn't react with %r in guild %s", settings["reaction_emoji"], message.guild.id)

    @tasks.loop(minutes=1)
    async def birthday_check(self) -> None:
        """Ping everyone whose level-up day has started in Atlanta and hasn't been announced yet.

        Polling (instead of firing exactly at midnight) means a restart around midnight won't skip anyone,
        and ``last_announced`` makes sure nobody is pinged twice.
        """
        today = atlanta_today()
        for guild in self.guilds:
            settings = self.storage.guild(guild.id)
            channel_id = settings["announcement_channel_id"] or settings["leaderboard_channel_id"]
            channel = guild.get_channel(channel_id) if channel_id else None
            if channel is None:
                continue

            levelled_up = False
            # Copy the items: commands may edit birthdays while we await sends.
            for user_id, birthday in list(settings["birthdays"].items()):
                if (
                    not is_birthday(birthday["month"], birthday["day"], today)
                    or birthday.get("last_announced") == today.isoformat()
                ):
                    continue
                level = level_on(birthday["day"], birthday["month"], birthday["year"], today)
                try:
                    await channel.send(
                        f"⬆️ **LEVEL UP!** ⬆️\n<@{user_id}> has reached **Level {level}**! "
                        "+1 to all stats. GG! 🎉"
                    )
                except discord.HTTPException:
                    log.exception("Couldn't send level-up message in guild %s", guild.id)
                    continue
                birthday["last_announced"] = today.isoformat()
                levelled_up = True

            if levelled_up:
                self.storage.save()
                await self.update_leaderboard(guild)

    @birthday_check.before_loop
    async def before_birthday_check(self) -> None:
        await self.wait_until_ready()

    async def update_leaderboard(self, guild: discord.Guild) -> None:
        """Edit the leaderboard message in place, or post a new one if it's missing."""
        settings = self.storage.guild(guild.id)
        channel_id = settings["leaderboard_channel_id"]
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            return

        today = atlanta_today()
        entries = []
        for user_id, birthday in settings["birthdays"].items():
            # Keep names fresh when we can see the member, otherwise use the name saved at registration.
            member = guild.get_member(int(user_id))
            if member is not None:
                birthday["name"] = member.display_name
            entries.append(
                (
                    birthday["name"],
                    level_on(birthday["day"], birthday["month"], birthday["year"], today),
                    date(birthday["year"], birthday["month"], birthday["day"]),
                )
            )
        content = render_leaderboard(entries)

        message_id = settings["leaderboard_message_id"]
        if message_id:
            try:
                await channel.get_partial_message(message_id).edit(content=content)
                self.storage.save()
                return
            except discord.NotFound:
                pass  # The old message was deleted; post a fresh one below.
            except discord.HTTPException:
                log.exception("Couldn't edit the leaderboard in guild %s", guild.id)
                return

        try:
            message = await channel.send(content)
        except discord.HTTPException:
            log.exception("Couldn't post the leaderboard in guild %s", guild.id)
            return
        settings["leaderboard_message_id"] = message.id
        self.storage.save()


class BirthdayCommands(app_commands.Group, name="birthday", description="Register your level-up day", guild_only=True):
    @app_commands.command(name="set", description="Set (or change) your birthday")
    @app_commands.describe(day="Day of the month", month="Month", year="Year you were born")
    @app_commands.choices(month=[app_commands.Choice(name=name, value=index + 1) for index, name in enumerate(MONTHS)])
    async def set_birthday(
        self,
        interaction: discord.Interaction["LevelUpBot"],
        day: app_commands.Range[int, 1, 31],
        month: app_commands.Choice[int],
        year: app_commands.Range[int, 1900, 9999],
    ) -> None:
        today = atlanta_today()
        try:
            birthdate = date(year, month.value, day)
        except ValueError:
            await interaction.response.send_message(f"{month.name} {day} isn't a real date in {year}.", ephemeral=True)
            return
        if birthdate > today:
            await interaction.response.send_message("You can't be born in the future!", ephemeral=True)
            return

        bot = interaction.client
        bot.storage.guild(interaction.guild_id)["birthdays"][str(interaction.user.id)] = {
            "day": day,
            "month": month.value,
            "year": year,
            "name": interaction.user.display_name,
            # Registering on the day itself shouldn't trigger a surprise ping; reactions still happen.
            "last_announced": today.isoformat() if is_birthday(month.value, day, today) else None,
        }
        bot.storage.save()

        level = level_on(day, month.value, year, today)
        await interaction.response.send_message(
            f"Saved! You're currently **Level {level}**. Your next level-up is on {month.name} {day}.",
            ephemeral=True,
        )
        await bot.update_leaderboard(interaction.guild)

    @app_commands.command(name="remove", description="Remove your birthday from the leaderboard")
    async def remove_birthday(self, interaction: discord.Interaction["LevelUpBot"]) -> None:
        bot = interaction.client
        if bot.storage.guild(interaction.guild_id)["birthdays"].pop(str(interaction.user.id), None) is None:
            await interaction.response.send_message("You don't have a birthday set.", ephemeral=True)
            return
        bot.storage.save()
        await interaction.response.send_message("Removed you from the leaderboard.", ephemeral=True)
        await bot.update_leaderboard(interaction.guild)


class SettingsCommands(
    app_commands.Group,
    name="levelup",
    description="Level Up Leaderboard settings",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
):
    @app_commands.command(name="emoji", description="Set the emoji used to react to messages on someone's level-up day")
    @app_commands.describe(emoji="A standard emoji or a custom emoji from this server")
    async def set_emoji(self, interaction: discord.Interaction["LevelUpBot"], emoji: str) -> None:
        emoji = emoji.strip()
        await interaction.response.send_message(f"Level-up day reactions will now use {emoji}")
        # Reacting with it is the simplest reliable way to check the bot can actually use this emoji.
        try:
            await (await interaction.original_response()).add_reaction(emoji)
        except discord.HTTPException:
            await interaction.edit_original_response(
                content=f"I can't react with `{emoji}`. Use a standard emoji or a custom emoji from this server."
            )
            return
        bot = interaction.client
        bot.storage.guild(interaction.guild_id)["reaction_emoji"] = emoji
        bot.storage.save()

    @app_commands.command(name="leaderboard-channel", description="Set the channel where the leaderboard is posted")
    async def set_leaderboard_channel(
        self, interaction: discord.Interaction["LevelUpBot"], channel: discord.TextChannel
    ) -> None:
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.view_channel and permissions.send_messages):
            await interaction.response.send_message(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return

        bot = interaction.client
        settings = bot.storage.guild(interaction.guild_id)
        old_channel = interaction.guild.get_channel(settings["leaderboard_channel_id"] or 0)
        old_message_id = settings["leaderboard_message_id"]
        settings["leaderboard_channel_id"] = channel.id
        settings["leaderboard_message_id"] = None
        bot.storage.save()
        await interaction.response.send_message(f"The leaderboard now lives in {channel.mention}.", ephemeral=True)

        if old_channel is not None and old_message_id:
            try:
                await old_channel.get_partial_message(old_message_id).delete()
            except discord.HTTPException:
                pass  # Already gone or no permission; nothing else to clean up.
        await bot.update_leaderboard(interaction.guild)

    @app_commands.command(
        name="announcement-channel",
        description="Set the channel for level-up pings (defaults to the leaderboard channel)",
    )
    async def set_announcement_channel(
        self, interaction: discord.Interaction["LevelUpBot"], channel: discord.TextChannel
    ) -> None:
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.view_channel and permissions.send_messages):
            await interaction.response.send_message(f"I can't send messages in {channel.mention}.", ephemeral=True)
            return

        bot = interaction.client
        bot.storage.guild(interaction.guild_id)["announcement_channel_id"] = channel.id
        bot.storage.save()
        await interaction.response.send_message(f"Level-up pings will go to {channel.mention}.", ephemeral=True)
