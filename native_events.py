"""Account-scoped event cursor selection and message identity validation."""

from datetime import datetime
from urllib.parse import quote

from .probe_native import NativeHTTPError, ProbeError, get_json

MAX_CURSOR = (1 << 63) - 1


def cursor_number(cursor):
    if not isinstance(cursor, str) or not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 19:
        raise ProbeError("invalid Native event cursor")
    value = int(cursor)
    if value > MAX_CURSOR:
        raise ProbeError("invalid Native event cursor")
    return value


async def latest_cursor(client, account):
    """Older Native rejects newest=true. Find its tail with bounded single-item queries."""
    url = account + "/events"
    try:
        page = await get_json(client, url, "latest event cursor", params={"newest": "true", "limit": "1"})
    except NativeHTTPError as error:
        if error.status != 400:
            raise
    else:
        return cursor_number(page.get("nextCursor"))

    async def page_after(cursor):
        try:
            page = await get_json(
                client, url, "event tail", params={"after": str(cursor), "limit": "1"}
            )
        except NativeHTTPError as error:
            if error.status == 410:
                return cursor + 1
            raise
        items = page.get("items")
        next_cursor = cursor_number(page.get("nextCursor"))
        if not isinstance(items, list) or len(items) > 1:
            raise ProbeError("invalid Native event page")
        if not items:
            if next_cursor != cursor:
                raise ProbeError("invalid empty Native event page")
            return cursor
        if next_cursor <= cursor:
            raise ProbeError("Native event cursor did not advance")
        return next_cursor

    upper = 0
    while True:
        next_cursor = await page_after(upper)
        if next_cursor == upper:
            break
        upper = min(MAX_CURSOR, max(upper * 2, next_cursor, 1))
    low = 0
    while low < upper:
        middle = (low + upper) // 2
        next_cursor = await page_after(middle)
        if next_cursor == middle:
            upper = middle
        else:
            low = next_cursor
    return low


def sticker_timestamp(message):
    if message.get("type") != 47 and not (
        message.get("type") == 49 and message.get("appMessageType") == 8
    ):
        return None
    try:
        created = datetime.fromisoformat(message.get("createdAt"))
        return int(created.timestamp()) if created.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def private_session(account, peer):
    return "|".join((quote(account, safe=""), "private", quote(peer, safe="")))
