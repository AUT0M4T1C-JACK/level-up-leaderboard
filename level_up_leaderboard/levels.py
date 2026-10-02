"""Birthday / level math and the ASCII leaderboard renderer.

Everything here is pure (no Discord) so it can be unit tested.
"""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

ATLANTA_TZ = ZoneInfo("America/New_York")

BAR_WIDTH = 30
NAME_WIDTH = 16
# Discord messages are capped at 2000 characters; stay well under it.
MAX_LEADERBOARD_CHARS = 1900


def atlanta_today() -> date:
    return datetime.now(ATLANTA_TZ).date()


def birthday_in_year(month: int, day: int, year: int) -> date:
    """Date the birthday is celebrated in ``year`` (Feb 29 falls back to Feb 28 in non-leap years)."""
    if month == 2 and day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)


def is_birthday(month: int, day: int, today: date) -> bool:
    return birthday_in_year(month, day, today.year) == today


def level_on(day: int, month: int, year: int, today: date) -> int:
    """The person's level (age) on ``today``."""
    return today.year - year - (today < birthday_in_year(month, day, today.year))


def render_leaderboard(entries: list[tuple[str, int, date]]) -> str:
    """Render ``(name, level, birthdate)`` entries as a ranked ASCII bar chart in a code block."""
    title = "LEVEL UP LEADERBOARD"
    if not entries:
        return f"```\n{title}\n\nNo one has registered yet. Use /birthday set to join!\n```"

    # Highest level first; ties go to whoever levelled up earliest (the older birthday).
    ranked = sorted(entries, key=lambda entry: (-entry[1], entry[2], entry[0].lower()))
    max_level = max(ranked[0][1], 1)
    rank_width = len(str(len(ranked)))
    level_width = len(str(max_level))

    lines = [title, "=" * len(title), ""]
    used = sum(len(line) + 1 for line in lines)
    for index, (name, level, _) in enumerate(ranked):
        # Backticks would break out of the code block.
        name = name.replace("`", "'")
        short_name = name if len(name) <= NAME_WIDTH else name[: NAME_WIDTH - 1] + "~"
        bar = "#" * max(round(level / max_level * BAR_WIDTH), 1 if level > 0 else 0)
        line = f"{index + 1:>{rank_width}}. {short_name:<{NAME_WIDTH}} Lv {level:>{level_width}} |{bar}"
        # Always keep room for the "... and N more" line.
        if used + len(line) + 1 > MAX_LEADERBOARD_CHARS - 30:
            lines.append(f"... and {len(ranked) - index} more")
            break
        lines.append(line)
        used += len(line) + 1

    return "```\n" + "\n".join(lines) + "\n```"
