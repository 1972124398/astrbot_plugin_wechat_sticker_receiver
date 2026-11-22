"""Match one genuine WeChat text to the immediately preceding sticker from its sender."""

from datetime import datetime
from urllib.parse import quote


def message_time(message):
    try:
        value = datetime.fromisoformat(message.get("createdAt"))
        return value.timestamp() if value.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def matches_session(session_id, account, thread, sender):
    group = thread.endswith("@chatroom")
    parts = [quote(account, safe=""), "group" if group else "private", quote(thread, safe="")]
    base = "|".join(parts)
    return session_id == base or (group and session_id == base + "|" + quote(sender, safe=""))


def is_sticker(message):
    return message.get("type") == 47 or (
        message.get("type") == 49 and message.get("appMessageType") == 8
    )


def previous_sticker(items, raw, ttl):
    """Native returns most recent first. The exact triggering message anchors the scan."""
    identity = (raw["accountId"], raw["threadId"], raw["senderId"])
    stamp = message_time(raw)
    if stamp is None:
        return None
    anchor = False
    for message in items:
        if not isinstance(message, dict):
            continue
        keys = tuple(message.get(key) for key in ("accountId", "threadId", "senderId"))
        if keys != identity or message.get("direction") != "incoming":
            continue
        if not anchor:
            anchor = message.get("id") == raw["id"]
            continue
        when = message_time(message)
        sticker_id = message.get("id")
        if (
            when is not None
            and 0 <= stamp - when <= ttl
            and is_sticker(message)
            and isinstance(sticker_id, str)
            and sticker_id
            and message.get("recall") is None
        ):
            return sticker_id
        return None
    return None
