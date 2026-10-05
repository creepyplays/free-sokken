#!/usr/bin/env python3
"""Post a daily Discord reminder about commenting for free socks. 🧦

Sends one message per day to a Discord webhook:

    🧦 Dag X van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok

The day number is stored in ``state.json`` and only goes up once per calendar
day, so running the script twice on the same day re-sends "Dag X" without
skipping a number. Everything can be configured with environment variables,
which are all optional except ``DISCORD_WEBHOOK_URL``:

    DISCORD_WEBHOOK_URL  the webhook URL (REQUIRED, keep it secret)
    MESSAGE_TEMPLATE     message template, ``{day}`` is replaced by the number
    WEBHOOK_USERNAME     display name of the bot in Discord
    STATE_FILE           where the day counter lives (default: state.json)
    TIMEZONE             timezone used to decide "today" (default: Europe/Amsterdam)

Usage:

    DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." python3 main.py
    python3 main.py --dry-run          # print the message, post nothing
    python3 main.py --day 42           # force a day number, leaves state alone
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:  # Python 3.9+; falls back to UTC when the tz database is missing.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

DEFAULT_MESSAGE = (
    "🧦 Dag {day} van te commenten tot ik gratis sokken krijg van nws.nws.nws. op TikTok"
)
DEFAULT_USERNAME = "Sokken Reminder"
DEFAULT_TIMEZONE = "Europe/Amsterdam"
DEFAULT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
USER_AGENT = "free-sokken-reminder/1.0 (+https://github.com/creepyplays/free-sokken)"
MAX_ATTEMPTS = 4


def today_str(timezone_name: str = DEFAULT_TIMEZONE) -> str:
    """Return today's date (YYYY-MM-DD) in the configured timezone."""
    tz = timezone.utc
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:  # unknown timezone name -> UTC is good enough
            pass
    return datetime.now(tz).date().isoformat()


def load_state(path: str) -> dict:
    """Read the day counter, tolerating a missing or corrupted file.

    ``day`` is the number the *next* reminder will use, ``last_posted`` the date
    (YYYY-MM-DD) of the last successful post and ``last_day`` the number that
    post used.
    """
    default = {"day": 1, "last_posted": None, "last_day": None}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        day = int(state.get("day", 1))
        last_posted = state.get("last_posted")
        last_day = state.get("last_day")
    except (OSError, ValueError, TypeError, AttributeError):
        return dict(default)

    if day < 1:
        day = 1
    if not isinstance(last_posted, str):
        last_posted = None
    if last_day is None:
        last_day = day - 1 if last_posted else None
    try:
        last_day = int(last_day) if last_day is not None else None
    except (TypeError, ValueError):
        last_day = None
    return {"day": day, "last_posted": last_posted, "last_day": last_day}


def resolve_day(state: dict, today: str, override: int | None = None) -> tuple[int, bool]:
    """Pick the day number to post and whether the counter should move on.

    Running twice on the same day repeats the same number ("Dag 1", "Dag 1")
    instead of skipping ahead to a day that hasn't happened yet.
    """
    if override is not None:
        return override, False
    if state["last_posted"] == today and state["last_day"]:
        return state["last_day"], False
    return state["day"], True


def save_state(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def build_message(template: str, day: int) -> str:
    """Fill ``{day}`` into the template, without blowing up on stray braces."""
    try:
        return template.format(day=day)
    except (KeyError, IndexError, ValueError):
        return template.replace("{day}", str(day))


def webhook_url_with_wait(webhook_url: str) -> str:
    """Ask Discord to return the created message as JSON instead of a bare 204."""
    parts = urllib.parse.urlsplit(webhook_url)
    query = urllib.parse.parse_qsl(parts.query)
    if not any(key == "wait" for key, _ in query):
        query.append(("wait", "true"))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def post_to_discord(webhook_url: str, content: str, username: str | None = None,
                    attempts: int = MAX_ATTEMPTS, timeout: int = 15) -> dict:
    """POST the message to Discord, retrying rate limits and server errors."""
    url = webhook_url_with_wait(webhook_url)
    payload: dict = {"content": content}
    if username:
        payload["username"] = username
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    last_error = "unknown error"

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except ValueError:
                    return {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            last_error = f"HTTP {error.code}: {detail}"
            retry_after = error.headers.get("Retry-After") or error.headers.get(
                "X-RateLimit-Reset-After"
            )
            if error.code == 429 or 500 <= error.code < 600:
                delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
            else:
                break  # 4xx (bad URL, deleted webhook, bad JSON) won't fix itself
        except urllib.error.URLError as error:
            last_error = f"network error: {error.reason}"
            delay = min(2 ** attempt, 30)

        if attempt < attempts:
            print(f"Retrying in {delay:.0f}s ({last_error})", file=sys.stderr)
            time.sleep(delay)

    raise SystemExit(f"Could not post to Discord after {attempts} attempts -> {last_error}")


def post_daily_reminder(state_file: str, dry_run: bool = False,
                        day_override: int | None = None, message_override: str | None = None,
                        webhook_url: str | None = None, username: str | None = None,
                        timezone_name: str = DEFAULT_TIMEZONE) -> dict:
    """Post today's reminder and advance the counter when a new day starts."""
    state = load_state(state_file)
    today = today_str(timezone_name)
    day, advance = resolve_day(state, today, day_override)
    template = message_override or os.environ.get("MESSAGE_TEMPLATE") or DEFAULT_MESSAGE
    message = build_message(template, day)

    print(message)
    if dry_run:
        print("[dry-run] nothing was posted, the day counter is untouched.")
        return {"posted": False, "day": day, "message": message}

    if not webhook_url:
        raise SystemExit(
            "DISCORD_WEBHOOK_URL is not set. Add it as an environment variable or as a "
            "repository secret (Settings -> Secrets and variables -> Actions). "
            "Use --dry-run to test without a webhook."
        )

    result = post_to_discord(webhook_url, message, username=username or DEFAULT_USERNAME)
    print(f"Posted to Discord (message id: {result.get('id', 'unknown')})")

    if advance:
        state["day"] = day + 1
        state["last_posted"] = today
        state["last_day"] = day
        save_state(state_file, state)
        print(f"Saved: the next reminder will be day {state['day']} ({state_file}).")
    elif day_override is None:
        print(f"Day {day} was already posted today ({today}); the counter is unchanged.")

    return {"posted": True, "day": day, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send the daily free-sokken Discord reminder.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the message instead of posting it (no state changes)")
    parser.add_argument("--state-file",
                        default=os.environ.get("STATE_FILE") or DEFAULT_STATE_FILE,
                        help="path to the day counter (default: state.json next to this script)")
    parser.add_argument("--day", type=int, default=None,
                        help="force a day number and leave the day counter untouched")
    parser.add_argument("--message", default=None,
                        help="message template for this run (default: MESSAGE_TEMPLATE)")
    parser.add_argument("--timezone",
                        default=os.environ.get("TIMEZONE") or DEFAULT_TIMEZONE,
                        help="timezone that decides when a new day starts")
    args = parser.parse_args(argv)

    post_daily_reminder(
        state_file=args.state_file,
        dry_run=args.dry_run or os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"},
        day_override=args.day,
        message_override=args.message,
        webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", "").strip(),
        username=os.environ.get("WEBHOOK_USERNAME") or None,
        timezone_name=args.timezone,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
