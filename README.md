# level-up-leaderboard
vibe coded discord bot for my friend server to celebrate people's birthdays

Birthdays are "level ups": your level is your age, and the bot keeps everyone ranked on an ASCII bar chart.

## Features
- `/birthday set day month year`: anyone can register or change their own birthday. Enter the month as a name (January) or number (1–12); month-name suggestions are available.
- `/birthday remove`: take yourself off the leaderboard.
- At midnight Atlanta time (`America/New_York`) on your birthday, the bot pings you with a **LEVEL UP!** message.
  If your birthday is Feb 29, it happens on Feb 28 in non-leap years.
- On your birthday, the bot reacts to every message you send with the configured emoji (default 🎂).
- The bot keeps one leaderboard message in a channel you choose and edits it whenever someone levels up or changes their birthday:
  ```
  LEVEL UP LEADERBOARD
  ====================

  1. Sam              Lv 31 |###############################
  2. Jack             Lv 29 |#############################
  3. Mo               Lv  8 |########
  ```

### Admin commands (need **Manage Server**)
- `/levelup emoji <emoji>`: set the birthday reaction emoji. Use a standard emoji or a custom emoji from this server.
- `/levelup leaderboard-channel <channel>`: choose where the leaderboard is posted.
- `/levelup announcement-channel <channel>`: choose where level-up pings go. If you don't set one, pings go to the leaderboard channel.

## Setup
1. Create an application and bot at <https://discord.com/developers/applications>, then copy the bot token.
   No privileged intents are needed.
2. Invite the bot with the `bot` and `applications.commands` scopes and these permissions:
   View Channels, Send Messages, Read Message History, Add Reactions.
3. Install and run it (Python 3.10+):
   ```sh
   pip install -r requirements.txt
   DISCORD_TOKEN=your-token-here python -m level_up_leaderboard
   ```
   Alternatively, put `DISCORD_TOKEN=your-token-here` in a `.env` file in the working directory
   (usually the repository root) and run `python -m level_up_leaderboard`.
   Exported environment variables take precedence over `.env` values. Keep your `.env` file private; it is git-ignored.
   Birthdays and settings are saved to `data.json`. Set `DATA_FILE` to store them somewhere else.
4. In your server, run `/levelup leaderboard-channel` to post the leaderboard. Then have everyone run `/birthday set`.

## Tests
```sh
python -m unittest
```
