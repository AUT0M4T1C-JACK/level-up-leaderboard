"""Tiny JSON-file store for per-server settings and birthdays."""

import json
import os
from pathlib import Path

DEFAULT_REACTION_EMOJI = "🎂"


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict = {"guilds": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        # Write to a temp file and swap it in so a crash mid-write can't corrupt the data.
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def guild(self, guild_id: int) -> dict:
        """Settings and birthdays for a server, created with defaults on first use."""
        return self.data["guilds"].setdefault(
            str(guild_id),
            {
                "reaction_emoji": DEFAULT_REACTION_EMOJI,
                "leaderboard_channel_id": None,
                "leaderboard_message_id": None,
                "announcement_channel_id": None,
                "birthdays": {},
            },
        )
