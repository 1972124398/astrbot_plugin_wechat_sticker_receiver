"""Convert genuine inbound WeChat stickers into AstrBot image components."""

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
import time
from urllib.parse import quote

import aiohttp
from PIL import Image as PillowImage

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.api.star import Star
from astrbot.core.agent.message import TextPart

from .native_events import cursor_number, latest_cursor, private_session, sticker_timestamp
from .probe_native import (
    MediaPending,
    NativeHTTPError,
    ProbeError,
    endpoint,
    event_candidates,
    get_json,
    inspect_media,
    stream_events,
)
from .render_sticker import render


RECENT_EVENT_SECONDS = 120
QUEUE_SIZE = 16
STICKER_CONTEXT = "（微信表情包，供理解这段聊天的语气和情绪。）"
STICKER_REPLY_GUIDANCE = (
    "把微信表情包当作对方说话时的语气。根据对方正在聊的内容自然接话。"
    "对方只发表情时，可以顺着情绪简短回应或接续上文。"
    "发出回复前，删掉对表情画面、动作、外观、文字的提及或猜测。"
)
STICKER_TURN_REMINDER = "【本轮表情】只用来体会对方的情绪。直接接话，省略对画面和动作的说明或猜测。"


def image_message(raw, account, own_username, timestamp, picture):
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = own_username
    message.session_id = private_session(account, raw["threadId"])
    message.message_id = raw["id"]
    message.sender = MessageMember(user_id=raw["senderId"], nickname=raw["senderId"])
    note = STICKER_CONTEXT
    if picture.preview:
        note += "（附图为静态预览。）"
    elif picture.sample_count > 1:
        note += "（附图为同一动图的顺序取样。）"
    message.message_str = note
    message.message = [Plain(note), Image.fromBytes(picture.png)]
    message.raw_message = raw
    message.timestamp = timestamp
    return message


class WeChatStickerReceiver(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.config = config
        self.client = None
        self.decoder = None
        self.tasks = ()
        self.queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.seen = deque(maxlen=512)

    async def initialize(self):
        self.account = self.config.get("account_id", "").strip()
        self.platform = self.config.get("platform_id", "").strip()
        self.peers = frozenset(self.config.get("private_peers", []))
        self.wait = max(300, min(10000, self.config.get("wait_ms", 4500))) / 1000
        if not self.account or not self.platform or not self.peers:
            logger.info("WeChat sticker receiver is waiting for an account and private conversation allowlist")
            return
        try:
            self.base = endpoint(self.config.get("native_origin", "http://127.0.0.1:6174"), self.account)
            path = Path(self.config.get("token_file", ""))
            if not path.is_absolute():
                raise ValueError("expected an absolute token file path")
            token = path.read_text(encoding="utf-8-sig").strip()
            if not token or not all(33 <= ord(char) <= 126 for char in token):
                raise ValueError("invalid token file")
        except (OSError, ValueError, ProbeError) as error:
            logger.warning("WeChat sticker receiver configuration rejected (%s)", type(error).__name__)
            return
        self.client = aiohttp.ClientSession(
            headers={"Authorization": "Bearer " + token},
            timeout=aiohttp.ClientTimeout(total=5),
            connector=aiohttp.TCPConnector(limit=4),
            trust_env=False,
            auto_decompress=False,
        )
        self.decoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wechat-sticker")
        self.tasks = (asyncio.create_task(self.listen()), asyncio.create_task(self.convert_messages()))

    async def terminate(self):
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = ()
        if self.client is not None:
            await self.client.close()
            self.client = None
        if self.decoder is not None:
            await asyncio.to_thread(self.decoder.shutdown, cancel_futures=True)
            self.decoder = None

    async def listen(self):
        cursor = None
        delay = 1
        client = self.client
        stream_timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=25)
        while True:
            try:
                if cursor is None:
                    cursor = await latest_cursor(client, self.base)
                async with client.get(
                    self.base + "/events/stream",
                    params={"after": str(cursor)},
                    headers={"Accept": "text/event-stream"},
                    timeout=stream_timeout,
                    allow_redirects=False,
                ) as response:
                    if response.status != 200 or response.content_type != "text/event-stream":
                        raise NativeHTTPError("event stream", response.status)
                    logger.info("WeChat sticker receiver listening on its own Native event stream")
                    delay = 1
                    async for frame in stream_events(response):
                        current = cursor_number(frame.get("cursor"))
                        if current <= cursor:
                            continue
                        data = frame.get("data")
                        if isinstance(data, dict):
                            thread = data.get("threadId")
                            if isinstance(thread, str) and thread in self.peers:
                                message_id = event_candidates(frame, thread)
                                if message_id is not None:
                                    try:
                                        self.queue.put_nowait((thread, message_id))
                                    except asyncio.QueueFull:
                                        logger.info("WeChat sticker receiver skipped an event while its queue was full")
                        cursor = current
            except NativeHTTPError as error:
                if error.status == 410:
                    cursor = None
                logger.warning("WeChat sticker receiver disconnected (%s)", error)
            except (aiohttp.ClientError, OSError, ProbeError, ValueError) as error:
                logger.warning("WeChat sticker receiver disconnected (%s)", type(error).__name__)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    def eligible_adapter(self, thread, sender):
        adapter = self.context.get_platform_inst(self.platform)
        if adapter is None or adapter.meta().name != "wechat_native" or getattr(adapter, "stopped", True):
            return None
        config = getattr(adapter, "native_config", None)
        guard = getattr(adapter, "loop_guard", None)
        if (
            config is None or config.account_id != self.account
            or not config.enable_private_reply or not config.enable_media
            or thread.endswith("@chatroom") or thread != sender
            or (config.allowed_users and sender not in config.allowed_users)
            or not getattr(adapter, "bot_self_id", None) or sender == adapter.bot_self_id
            or guard is None or guard.blocked(thread)
        ):
            return None
        return adapter

    async def download(self, url, message_id):
        transfer_requested = False
        while True:
            try:
                return await inspect_media(self.client, self.base, url, self.account, message_id, report=False)
            except MediaPending as error:
                if not transfer_requested:
                    async with self.client.post(
                        url + "/media-transfers",
                        json={"messageId": message_id, "assetId": error.asset_id, "quality": "best"},
                        allow_redirects=False,
                    ) as response:
                        if response.status != 202:
                            raise NativeHTTPError("media transfer", response.status) from None
                    transfer_requested = True
                await asyncio.sleep(0.2)

    async def convert_message(self, thread, message_id):
        if message_id in self.seen or self.eligible_adapter(thread, thread) is None:
            return
        url = self.base + "/messages/" + quote(message_id, safe="")
        raw = await get_json(self.client, url, "Native message")
        timestamp = sticker_timestamp(raw)
        if (
            timestamp is None or not -30 <= time.time() - timestamp <= RECENT_EVENT_SECONDS
            or raw.get("accountId") != self.account or raw.get("threadId") != thread
            or raw.get("senderId") != thread or raw.get("id") != message_id
            or raw.get("direction") != "incoming" or raw.get("recall") is not None
        ):
            return
        logger.info("WeChat sticker receiver got an inbound sticker")
        blob, preview = await self.download(url, message_id)
        picture = await asyncio.get_running_loop().run_in_executor(
            self.decoder, partial(render, blob, preview=preview)
        )
        current = await get_json(self.client, url, "sticker validity")
        adapter = self.eligible_adapter(thread, thread)
        identity_fields = ("accountId", "threadId", "senderId", "id", "serverId", "direction", "type", "appMessageType")
        if (
            adapter is None or current.get("recall") is not None
            or any(current.get(field) != raw.get(field) for field in identity_fields)
        ):
            return
        message = image_message(raw, self.account, adapter.bot_self_id, timestamp, picture)
        try:
            event = adapter.create_event(message)
            event.set_extra("wechat_sticker_context", True)
            adapter.commit_event(event)
        except asyncio.QueueFull:
            logger.info("WeChat sticker receiver skipped delivery while the AstrBot queue was full")
            return
        self.seen.append(message_id)
        logger.info(
            "WeChat sticker receiver delivered a sticker image with context frames=%s preview=%s bounded=%s",
            picture.sample_count, picture.preview, picture.limited,
        )

    async def convert_messages(self):
        while True:
            thread, message_id = await self.queue.get()
            try:
                async with asyncio.timeout(self.wait):
                    await self.convert_message(thread, message_id)
            except ProbeError as error:
                logger.info("WeChat sticker receiver skipped media (%s)", error)
            except (aiohttp.ClientError, OSError, ValueError, PillowImage.DecompressionBombError) as error:
                logger.info("WeChat sticker receiver skipped media (%s)", type(error).__name__)
            finally:
                self.queue.task_done()

    @filter.on_llm_request(priority=-50)
    async def frame_sticker_context(self, event, request):
        if (
            self.client is None
            or event.get_platform_name() != "wechat_native"
            or event.get_platform_id() != self.platform
            or event.get_group_id()
            or event.get_sender_id() not in self.peers
        ):
            return
        native_sticker = event.get_extra("wechat_sticker_context") is True
        merged_sticker = STICKER_CONTEXT in (request.prompt or "") and bool(request.image_urls)
        if native_sticker or merged_sticker:
            system_prompt = request.system_prompt or ""
            if not system_prompt.endswith(STICKER_REPLY_GUIDANCE):
                request.system_prompt = (
                    system_prompt + "\n\n" + STICKER_REPLY_GUIDANCE
                    if system_prompt else STICKER_REPLY_GUIDANCE
                )
                request.extra_user_content_parts.append(TextPart(text=STICKER_TURN_REMINDER).mark_as_temp())
                logger.info("WeChat sticker receiver added reply context for the sticker turn")
