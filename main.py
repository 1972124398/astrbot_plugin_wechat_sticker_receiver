"""AstrBot request hook for opt-in, one-turn WeChat sticker context."""

import asyncio
import base64
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import time
from pathlib import Path
from urllib.parse import quote

import aiohttp
from PIL import Image

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.core.agent.message import ImageURLPart

from .association import matches_session, message_time, previous_sticker
from .probe_native import MediaPending, ProbeError, endpoint, get_json, inspect_media
from .render_sticker import render


class WeChatStickerReceiver(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.config = config
        self.client = None
        self.decoder = None
        self.pending = set()
        self.claims = OrderedDict()

    async def initialize(self):
        self.account = self.config.get("account_id", "").strip()
        self.platform = self.config.get("platform_id", "").strip()
        self.peers = frozenset(self.config.get("private_peers", []))
        self.groups = frozenset(self.config.get("groups", []))
        self.ttl = max(10, min(600, self.config.get("ttl_seconds", 120)))
        self.wait = max(100, min(3000, self.config.get("wait_ms", 1400))) / 1000
        path = Path(self.config.get("token_file", ""))
        if not self.account or not self.platform or not (self.peers or self.groups):
            logger.info("WeChat sticker receiver is waiting for an account and conversation allowlist")
            return
        try:
            self.base = endpoint(self.config.get("native_origin", "http://127.0.0.1:6174"), self.account)
            if not path.is_absolute():
                raise ValueError("expected an absolute token file path")
            token = path.read_text(encoding="utf-8-sig").strip()
            if not token or not all(33 <= ord(char) <= 126 for char in token):
                raise ValueError("invalid token file")
        except (OSError, ValueError, ProbeError) as exc:
            logger.warning("WeChat sticker receiver configuration rejected (%s)", type(exc).__name__)
            return
        self.client = aiohttp.ClientSession(
            headers={"Authorization": "Bearer " + token},
            timeout=aiohttp.ClientTimeout(total=self.wait),
            connector=aiohttp.TCPConnector(limit=4),
            trust_env=False,
            auto_decompress=False,
        )
        self.decoder = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wechat-sticker")
        logger.info("WeChat sticker receiver ready")

    async def terminate(self):
        client, self.client = self.client, None
        tasks = tuple(self.pending)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if client is not None:
            await client.close()
        if self.decoder is not None:
            await asyncio.to_thread(self.decoder.shutdown, cancel_futures=True)
            self.decoder = None
        self.claims.clear()

    def current_native_message(self, event, request):
        if (
            event.get_platform_name() != "wechat_native"
            or event.get_platform_id() != self.platform
            or request.image_urls
            or request.audio_urls
            or any(
                (part.get("type") if isinstance(part, dict) else getattr(part, "type", None))
                == "image_url"
                for part in request.extra_user_content_parts
            )
            or event.get_extra("wechat_sticker_receiver_attached") is request
        ):
            return None
        raw = event.message_obj.raw_message
        if not isinstance(raw, dict):
            return None
        thread, sender = raw.get("threadId"), raw.get("senderId")
        stamp = message_time(raw)
        if (
            not isinstance(thread, str) or not thread
            or not isinstance(sender, str) or not sender
            or not isinstance(raw.get("id"), str) or not raw["id"]
            or raw["id"] != event.message_obj.message_id
            or raw.get("accountId") != self.account
            or raw.get("direction") != "incoming"
            or raw.get("type") != 1
            or raw.get("recall") is not None
            or stamp is None
            or not -30 <= time.time() - stamp <= self.ttl
            or sender != event.get_sender_id()
            or sender == event.get_self_id()
            or not matches_session(event.get_session_id(), self.account, thread, sender)
        ):
            return None
        if thread.endswith("@chatroom"):
            return raw if event.get_group_id() == thread and thread in self.groups else None
        return raw if not event.get_group_id() and thread == sender and sender in self.peers else None

    async def load_visual(self, client, message):
        thread = self.base + "/threads/" + quote(message["threadId"], safe="")
        page = await get_json(client, thread + "/messages", "thread messages", params={"limit": 32})
        items = page.get("items")
        if not isinstance(items, list):
            raise ProbeError("invalid thread message list")
        sticker_id = previous_sticker(items, message, self.ttl)
        if sticker_id is None:
            return None
        logger.info("WeChat sticker receiver matched a recent message")
        url = self.base + "/messages/" + quote(sticker_id, safe="")
        transfer_requested = False
        while True:
            try:
                blob, preview = await inspect_media(
                    client, self.base, url, self.account, sticker_id, report=False
                )
                break
            except MediaPending as error:
                if not transfer_requested:
                    async with client.post(
                        url + "/media-transfers",
                        json={"messageId": sticker_id, "assetId": error.asset_id, "quality": "best"},
                        allow_redirects=False,
                    ) as response:
                        if response.status != 202:
                            raise ProbeError(f"media transfer: HTTP {response.status}") from None
                    transfer_requested = True
                await asyncio.sleep(0.2)
        picture = await asyncio.get_running_loop().run_in_executor(
            self.decoder, partial(render, blob, preview=preview)
        )
        return sticker_id, picture

    @filter.on_llm_request()
    async def add_sticker_image(self, event, request):
        client = self.client
        if client is None or len(self.pending) >= 4:
            return
        message = self.current_native_message(event, request)
        if message is None:
            return
        try:
            provider = await self.context.get_using_provider_async(event.unified_msg_origin)
        except (LookupError, ValueError):
            return
        if provider is None or "image" not in provider.provider_config.get("modalities", []):
            return
        task = asyncio.create_task(self.load_visual(client, message))
        self.pending.add(task)
        try:
            result = await asyncio.wait_for(task, self.wait)
        except ProbeError as exc:
            logger.info("WeChat sticker receiver skipped unavailable media (%s)", exc)
            return
        except (OSError, ValueError, aiohttp.ClientError, Image.DecompressionBombError) as exc:
            logger.info("WeChat sticker receiver skipped unavailable media (%s)", type(exc).__name__)
            return
        except asyncio.CancelledError:
            if self.client is not None:
                raise
            return
        finally:
            self.pending.discard(task)
        if result is None or self.client is not client:
            return
        sticker_id, picture = result
        now = time.monotonic()
        while self.claims and next(iter(self.claims.values()))[1] <= now:
            self.claims.popitem(last=False)
        claim = self.claims.get(sticker_id)
        if claim is not None and claim[0] != message["id"]:
            return
        self.claims.pop(sticker_id, None)
        self.claims[sticker_id] = (message["id"], now + self.ttl)
        if len(self.claims) > 256:
            self.claims.popitem(last=False)
        encoded = base64.b64encode(picture.png).decode("ascii")
        image = ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64," + encoded))
        request.extra_user_content_parts.append(image.mark_as_temp())
        event.set_extra("wechat_sticker_receiver_attached", request)
        logger.info(
            "WeChat sticker receiver attached image frames=%s preview=%s bounded=%s",
            picture.sample_count,
            picture.preview,
            picture.limited,
        )

    @filter.on_llm_response()
    async def observe_sticker_turn(self, event, response):
        if event.get_extra("wechat_sticker_receiver_attached") is not None:
            logger.info("WeChat sticker receiver observed a response to the image-augmented turn")
