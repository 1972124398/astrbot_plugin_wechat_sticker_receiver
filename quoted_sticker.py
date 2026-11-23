"""Resolve quoted stickers without mixing accounts, chats or quote sources."""

from urllib.parse import quote

from .probe_native import ProbeError, get_json


IDENTITY_FIELDS = (
    "accountId", "threadId", "senderId", "id", "serverId", "direction", "type", "appMessageType",
)


def is_sticker(raw):
    return isinstance(raw, dict) and (
        raw.get("type") == 47 or (raw.get("type") == 49 and raw.get("appMessageType") == 8)
    )


def quoted_sticker(raw):
    if not isinstance(raw, dict) or raw.get("type") != 49 or raw.get("appMessageType") != 57:
        return False
    reference = raw.get("quote")
    if raw.get("recall") is not None or not is_sticker(reference):
        return False
    if reference.get("state") == "embedded":
        return reference.get("embeddedSticker") is True
    return reference.get("state") == "missing" and all(
        isinstance(reference.get(key), str) and bool(reference[key])
        for key in ("serverId", "senderId")
    )


def check_quote(current, raw):
    if (
        not quoted_sticker(current)
        or any(current.get(field) != raw.get(field) for field in IDENTITY_FIELDS)
        or current.get("quote") != raw.get("quote")
    ):
        raise ProbeError("quoted sticker changed or was recalled")


def check_original(original, raw, message_id):
    reference = raw["quote"]
    if (
        not is_sticker(original) or original.get("recall") is not None
        or original.get("id") != message_id
        or any(original.get(key) != raw.get(key) for key in ("accountId", "threadId"))
        or any(original.get(key) != reference.get(key) for key in ("serverId", "senderId", "type"))
        or (reference["type"] == 49 and original.get("appMessageType") != reference.get("appMessageType"))
    ):
        raise ProbeError("quoted sticker original unavailable")


def message_url(base, message_id):
    return base + "/messages/" + quote(message_id, safe="")


async def resolve_source(client, base, raw, state=None):
    """Embedded media belongs to the reply; missing quotes can use a verified original."""
    if not quoted_sticker(raw):
        raise ProbeError("quoted sticker unavailable")
    reference = raw["quote"]
    if state is not None and state.is_recalled(raw["threadId"], reference.get("serverId")):
        raise ProbeError("quoted sticker recalled")
    if reference["state"] == "embedded":
        return raw["id"], True
    original_id = state.find_message_id(raw["threadId"], reference["serverId"]) if state else None
    if not original_id:
        listing = await get_json(
            client, base + "/threads/" + quote(raw["threadId"], safe="") + "/messages",
            "quoted sticker lookup", params={"limit": "50"},
        )
        items = listing.get("items")
        if not isinstance(items, list) or len(items) > 50:
            raise ProbeError("invalid quoted sticker lookup")
        matches = [
            item for item in items
            if isinstance(item, dict) and item.get("serverId") == reference["serverId"]
        ]
        if len(matches) != 1:
            raise ProbeError("quoted sticker original not found")
        original_id = matches[0].get("id")
    if not isinstance(original_id, str) or not original_id or original_id == raw["id"]:
        raise ProbeError("invalid quoted sticker original")
    await recheck_original(client, base, raw, original_id, state)
    return original_id, False


async def recheck_original(client, base, raw, message_id, state=None):
    if state is not None and (
        state.message_status(message_id) == "recalled"
        or state.is_recalled(raw["threadId"], raw["quote"].get("serverId"))
    ):
        raise ProbeError("quoted sticker recalled")
    original = await get_json(client, message_url(base, message_id), "quoted sticker validity")
    check_original(original, raw, message_id)
