"""Observe one consented Native conversation using a separate, read-only SSE stream."""

import argparse
import asyncio
from collections import Counter
from hashlib import sha256
from io import BytesIO
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

import aiohttp
from PIL import Image


MAX_MEDIA_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_EVENT_BYTES = 1024 * 1024
SUPPORTED_FORMATS = ("PNG", "GIF", "WEBP", "JPEG")


class ProbeError(Exception):
    pass


class MediaPending(ProbeError):
    def __init__(self, asset_id):
        super().__init__("sticker media pending")
        self.asset_id = asset_id


def endpoint(origin, account):
    parsed = urlsplit(origin)
    if parsed.hostname != "localhost":
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = False
        if not is_loopback:
            raise ProbeError("expected a loopback Native URL")
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ProbeError("expected a Native origin without credentials or path")
    return origin.rstrip("/") + "/v1/accounts/" + quote(account, safe="")


def event_candidates(frame, thread):
    kind = frame.get("kind")
    data = frame.get("data")
    if kind != "message.committed" or not isinstance(data, dict):
        return None
    if data.get("threadId") != thread or data.get("origin") != "live":
        return None
    value = data.get("messageId")
    return value if isinstance(value, str) and value else None


async def get_json(client, url, label, **kwargs):
    async with client.get(url, allow_redirects=False, **kwargs) as response:
        if response.status != 200:
            raise ProbeError(f"{label}: HTTP {response.status}")
        data = await bounded_read(response, MAX_EVENT_BYTES)
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ProbeError(f"{label}: invalid response envelope")
        return result


async def bounded_read(response, limit):
    data = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        data.extend(chunk)
        if len(data) > limit:
            raise ProbeError("response exceeds byte limit")
    return bytes(data)


async def stream_events(response):
    data = []
    frame_bytes = 0
    async for raw in response.content:
        if raw.startswith(b":"):
            continue
        if not raw.strip():
            if data:
                value = json.loads(b"\n".join(data))
                if not isinstance(value, dict):
                    raise ProbeError("invalid SSE payload")
                if "error" in value:
                    raise ProbeError("Native emitted an SSE error")
                yield value
            data.clear()
            frame_bytes = 0
        elif raw.startswith(b"data:"):
            frame_bytes += len(raw)
            if frame_bytes > MAX_EVENT_BYTES:
                raise ProbeError("SSE event exceeds byte limit")
            data.append(raw[5:].removesuffix(b"\n").removesuffix(b"\r").removeprefix(b" "))


async def inspect_asset(client, base, asset, metadata, preview, *, representation=False, report=True):
    asset_id = asset.get("id")
    count = metadata.get("byteLength")
    digest = metadata.get("sha256")
    if (
        not isinstance(asset_id, str)
        or not asset_id
        or type(count) is not int
        or not 0 < count <= MAX_MEDIA_BYTES
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-fA-F0-9]{64}", digest)
    ):
        raise ProbeError("invalid or oversized media metadata")
    url = base + "/media/" + quote(asset_id, safe="") + "/content"
    params = {"representation": "preview"} if representation else None
    async with client.get(url, params=params, allow_redirects=False) as response:
        if response.status != 200:
            raise ProbeError(f"media content: HTTP {response.status}")
        blob = await bounded_read(response, count)
    if len(blob) != count or sha256(blob).hexdigest() != digest.lower():
        raise ProbeError("media length or digest mismatch")
    if report:
        with Image.open(BytesIO(blob), formats=SUPPORTED_FORMATS) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ProbeError("image exceeds pixel limit")
            image.load()
            print(
                f"decoded sticker format={image.format} dimensions={image.width}x{image.height} "
                f"animated={getattr(image, 'is_animated', False)} preview={preview}",
                flush=True,
            )
    return blob, preview


async def inspect_media(client, base, message_url, account, message_id, *, report=True):
    result = await get_json(client, message_url + "/media", "media metadata")
    items = result.get("items")
    if not isinstance(items, list):
        raise ProbeError("invalid media asset list")
    ready = []
    pending = None
    for asset in items:
        if (
            not isinstance(asset, dict)
            or asset.get("accountId") != account
            or asset.get("messageId") != message_id
            or asset.get("kind") != "sticker"
            or asset.get("source") not in ("message", None)
        ):
            continue
        state = asset.get("state")
        known_states = ("available", "pending", "expired", "unsupported", "recalled")
        safe_state = state if state in known_states else "unknown"
        if report:
            print(f"sticker asset state={safe_state}", flush=True)
        asset_id = asset.get("id")
        if (
            state in ("pending", "queued", "downloading")
            and isinstance(asset_id, str)
            and asset_id
            and asset.get("variant") in ("original", "thumbnail", "preview")
            and (pending is None or asset["variant"] == "original")
        ):
            pending = asset_id
        if state != "available":
            continue
        is_preview = (asset.get("actualVariant") or asset.get("variant")) != "original"
        preview = asset.get("preview")
        if asset.get("contentType") != "image/x-wxgf":
            ready.append((is_preview, asset, asset, False))
        if isinstance(preview, dict) and preview.get("sourceSha256") == asset.get("sha256"):
            ready.append((True, asset, preview, True))
    for is_preview, asset, metadata, representation in sorted(ready, key=lambda value: value[0]):
        try:
            return await inspect_asset(
                client, base, asset, metadata, is_preview, representation=representation, report=report
            )
        except ProbeError as error:
            if report:
                print(f"sticker asset rejected ({error})", flush=True)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as error:
            if report:
                print(f"sticker asset rejected ({type(error).__name__})", flush=True)
    if pending:
        raise MediaPending(pending)
    raise ProbeError("no available sticker asset")


async def inspect_message(client, base, message_id, args, counts):
    url = base + "/messages/" + quote(message_id, safe="")
    message = await get_json(client, url, "message read")
    if (
        message.get("accountId") != args.account
        or message.get("threadId") != args.thread
        or message.get("id") != message_id
        or message.get("senderId") != args.sender
        or message.get("direction") != "incoming"
        or message.get("recall") is not None
    ):
        return
    kind, subtype = message.get("type"), message.get("appMessageType")
    if kind == 1:
        counts["texts"] += 1
        print("live text identity matched", flush=True)
    elif kind == 47 or (kind == 49 and subtype == 8):
        counts["stickers"] += 1
        print(f"live sticker identity matched type={kind} subtype={subtype if kind == 49 else '-'}", flush=True)
        try:
            await inspect_media(client, base, url, args.account, message_id)
        except ProbeError as error:
            print(f"media unavailable ({error})", flush=True)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as error:
            print(f"media unavailable ({type(error).__name__})", flush=True)
        else:
            counts["decoded"] += 1


async def run(args):
    base = endpoint(args.origin, args.account)
    token = args.token_file.read_text(encoding="utf-8-sig").strip()
    if not token or not token.isascii() or not all(33 <= ord(char) <= 126 for char in token):
        raise ProbeError("invalid token file")
    auth = {"Authorization": "Bearer " + token}
    http_timeout = aiohttp.ClientTimeout(total=6)
    counts = Counter()
    async with aiohttp.ClientSession(
        headers=auth, timeout=http_timeout, trust_env=False, auto_decompress=False
    ) as client:
        await get_json(client, base, "account status")
        if args.check:
            print("Native account status: HTTP 200", flush=True)
            return
        if args.after is None:
            page = await get_json(client, base + "/events", "latest event cursor", params={
                "newest": "true", "limit": "1",
            })
            cursor = page.get("nextCursor")
        else:
            cursor = args.after
        if not isinstance(cursor, str) or not re.fullmatch(r"[0-9]{1,19}", cursor):
            raise ProbeError("missing or invalid event cursor")
        stream_timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=20)
        try:
            async with asyncio.timeout(args.seconds):
                async with client.get(
                    base + "/events/stream",
                    params={"after": cursor},
                    headers={"Accept": "text/event-stream"},
                    timeout=stream_timeout,
                    allow_redirects=False,
                ) as response:
                    if response.status != 200 or response.content_type != "text/event-stream":
                        raise ProbeError(f"event stream: HTTP {response.status}")
                    print("independent event stream connected", flush=True)
                    async for frame in stream_events(response):
                        message_id = event_candidates(frame, args.thread)
                        if message_id is not None:
                            await inspect_message(client, base, message_id, args, counts)
                            if counts["texts"] and counts["decoded"]:
                                break
        except TimeoutError:
            pass
    print(f"matched texts={counts['texts']} stickers={counts['stickers']} decoded={counts['decoded']}")
    if not counts["texts"] or not counts["decoded"]:
        raise ProbeError("one matched text and one decoded sticker are required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:6174")
    parser.add_argument("--account", required=True)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--thread")
    parser.add_argument("--sender")
    parser.add_argument("--after", help="Explicit starting cursor for older Native releases")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--check", action="store_true", help="Check only the account status route")
    args = parser.parse_args()
    if not args.check and (not args.thread or not args.sender or not 1 <= args.seconds <= 600):
        parser.error("live mode requires --thread, --sender and --seconds between 1 and 600")
    try:
        asyncio.run(run(args))
    except ProbeError as error:
        parser.exit(1, f"probe failed: {error}\n")
    except (OSError, ValueError, aiohttp.ClientError) as error:
        parser.exit(1, f"probe failed: {type(error).__name__}\n")


if __name__ == "__main__":
    main()
