import re
from datetime import datetime
import logging


BOT_REGEX = re.compile(r"\b(bot|botting|bots|cheating bot|poker bot|AI bot|GTO bot)\b", re.IGNORECASE)

def clean_text(text):
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return re.sub(r'\s+', ' ', text).encode("ascii", "ignore").decode()

import re
from datetime import datetime

def clean_date(date_text):
    """
    Converts an extracted date string into MySQL datetime.
    Supports multiple formats, including 'MM-DD-YYYY, HH:MM PM'.
    """
    if not date_text or not date_text.strip():
        return "0000-00-00 00:00:00"

    dt_str = date_text.strip()

    # If they use "Today" or "Yesterday", you could handle that here:
    # if dt_str.lower().startswith("today"):
    #     today = datetime.today().strftime("%Y-%m-%d")
    #     # extract time portion and combine...
    #     ...

    # Try all known formats
    formats = [
        "%Y-%m-%d %H:%M:%S",       # e.g. "2025-03-02 01:33:00"
        "%b %d, %Y, %I:%M %p",     # e.g. "Jul 02, 2023, 07:55 PM"
        "%d %b %Y %H:%M",          # e.g. "02 Jul 2023 19:55"
        "%m-%d-%Y, %I:%M %p",      # **NEW** e.g. "07-02-2023, 07:55 PM"
        "%m-%d-%Y %I:%M %p",       # e.g. "07-02-2023 07:55 PM"
        "%m-%d-%Y"                 # e.g. "07-02-2023"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    # If nothing matched, log and return invalid placeholder
    logging.error(f"Failed to parse date: {date_text}")
    return "0000-00-00 00:00:00"


def contains_bot_mention(content):
    return int(bool(BOT_REGEX.search(content)))
