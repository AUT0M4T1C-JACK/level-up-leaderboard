import logging
import os
import sys

from .bot import LevelUpBot
from .storage import Storage

token = os.environ.get("DISCORD_TOKEN")
if not token:
    sys.exit("Set the DISCORD_TOKEN environment variable to your bot token.")

bot = LevelUpBot(Storage(os.environ.get("DATA_FILE", "data.json")))
bot.run(token, log_level=logging.INFO)
