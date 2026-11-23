"""Exercise event enrichment with real AstrBot components when AstrBot is installed."""

import asyncio
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    # AstrBot initializes runtime files during import; keep them out of the checkout.
    with tempfile.TemporaryDirectory(prefix="sticker-test-") as runtime_root:
        with patch.dict(os.environ, {"ASTRBOT_ROOT": runtime_root}):
            from astrbot_plugin_wechat_sticker_receiver import main as plugin
            from astrbot.api.message_components import Image, Plain, Reply
except ModuleNotFoundError as error:
    if not error.name.startswith("astrbot") or error.name.startswith("astrbot_plugin"):
        raise
    plugin = None

from astrbot_plugin_wechat_sticker_receiver.render_sticker import Visual
from test_quoted_sticker import reply


@unittest.skipIf(plugin is None, "AstrBot runtime is required for event integration")
class EventIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.receiver = object.__new__(plugin.WeChatStickerReceiver)
        self.receiver.client = object()
        self.receiver.platform = "wechat"
        self.receiver.account = "a"
        self.receiver.peers = frozenset({"peer"})
        self.receiver.base = "http://127.0.0.1:6174/v1/accounts/a"
        self.receiver.wait = 0.2
        self.adapter = SimpleNamespace(
            stopped=False, bot_self_id="self", meta=lambda: SimpleNamespace(name="wechat_native"),
            native_config=SimpleNamespace(
                account_id="a", enable_private_reply=True, enable_media=True, allowed_users=[],
            ),
            loop_guard=SimpleNamespace(blocked=lambda thread: False),
        )
        self.receiver.context = SimpleNamespace(get_platform_inst=lambda platform: self.adapter)
        self.extras = {}
        raw = reply()
        self.message = SimpleNamespace(
            message_id=raw["id"], raw_message=raw, message_str=raw["body"],
            message=[Reply(id="900", sender_id="peer", message_str="引用消息内容不可用"), Plain(raw["body"])],
        )
        self.event = SimpleNamespace(
            message_obj=self.message, message_str=raw["body"],
            get_platform_name=lambda: "wechat_native", get_platform_id=lambda: "wechat",
            get_group_id=lambda: "", get_sender_id=lambda: "peer",
            get_extra=lambda key: self.extras.get(key),
            set_extra=lambda key, value: self.extras.update({key: value}),
            get_messages=lambda: self.message.message,
            get_message_str=lambda: self.event.message_str,
        )
        self.json = AsyncMock(side_effect=lambda *a, **kw: copy.deepcopy(raw))
        self.json_patch = patch.object(plugin, "get_json", self.json)
        self.json_patch.start()
        self.addCleanup(self.json_patch.stop)
        self.receiver.render_message = AsyncMock(return_value=Visual(b"png", 4, False, False))

    async def test_quote_enriches_existing_event_once_preserving_text_and_identity(self):
        await self.receiver.attach_quoted_sticker(self.event)
        await self.receiver.attach_quoted_sticker(self.event)
        self.receiver.render_message.assert_awaited_once_with(
            self.receiver.base + "/messages/reply%2F1", "reply/1", quoted=True,
        )
        self.assertEqual(self.message.message_id, "reply/1")
        self.assertEqual(self.message.message[0].id, "900")
        self.assertEqual(self.message.message[0].sender_id, "peer")
        self.assertEqual(self.message.message[1].text, reply()["body"])
        self.assertIn("顺序取样", self.message.message[0].message_str)
        self.assertIsInstance(self.message.message[-1], Image)
        self.assertTrue(self.event.message_str.startswith(reply()["body"]))
        self.assertEqual(self.message.message_str, self.event.message_str)

    async def test_parent_recalled_during_download_keeps_text_without_image(self):
        self.json.side_effect = [reply(), reply(recall={})]
        await self.receiver.attach_quoted_sticker(self.event)
        self.assertEqual(len(self.message.message), 2)
        self.assertEqual(self.event.message_str, reply()["body"])
        self.assertFalse(self.extras)

    async def test_timeout_keeps_original_message(self):
        self.receiver.render_message.side_effect = TimeoutError
        await self.receiver.attach_quoted_sticker(self.event)
        self.assertEqual(len(self.message.message), 2)
        self.assertEqual(self.event.message_str, reply()["body"])

    async def test_adapter_supplied_image_is_not_duplicated(self):
        self.message.message.append(Image.fromBytes(b"already converted"))
        await self.receiver.attach_quoted_sticker(self.event)
        self.receiver.render_message.assert_not_awaited()
        self.json.assert_not_awaited()

    async def test_other_platform_group_and_unallowed_peer_are_ignored(self):
        for method, value in (
            ("get_platform_name", "other"), ("get_platform_id", "other"),
            ("get_group_id", "room@chatroom"), ("get_sender_id", "other"),
        ):
            previous = getattr(self.event, method)
            setattr(self.event, method, lambda: value)
            await self.receiver.attach_quoted_sticker(self.event)
            setattr(self.event, method, previous)
        self.receiver.render_message.assert_not_awaited()

    async def test_quote_guidance_preserves_explicit_questions_and_survives_merge(self):
        request = SimpleNamespace(
            prompt="合并的文字\n" + plugin.QUOTED_STICKER_CONTEXT, image_urls=["image"],
            system_prompt="原有人设", extra_user_content_parts=[],
        )
        await self.receiver.frame_sticker_context(self.event, request)
        await self.receiver.frame_sticker_context(self.event, request)
        self.assertTrue(request.system_prompt.startswith("原有人设"))
        self.assertTrue(request.system_prompt.endswith(plugin.QUOTED_STICKER_GUIDANCE))
        self.assertNotIn(plugin.STICKER_REPLY_GUIDANCE, request.system_prompt)
        self.assertEqual(len(request.extra_user_content_parts), 1)

    async def test_direct_sticker_guidance_is_retained(self):
        self.extras["wechat_sticker_context"] = True
        request = SimpleNamespace(
            prompt=plugin.STICKER_CONTEXT, image_urls=["image"],
            system_prompt="", extra_user_content_parts=[],
        )
        await self.receiver.frame_sticker_context(self.event, request)
        self.assertEqual(request.system_prompt, plugin.STICKER_REPLY_GUIDANCE)

    async def test_direct_worker_survives_a_media_timeout(self):
        self.receiver.queue = asyncio.Queue()
        self.receiver.convert_message = AsyncMock(side_effect=[TimeoutError, None])
        await self.receiver.queue.put(("peer", "first"))
        await self.receiver.queue.put(("peer", "second"))
        worker = asyncio.create_task(self.receiver.convert_messages())
        try:
            await asyncio.wait_for(self.receiver.queue.join(), 1)
            self.assertEqual(self.receiver.convert_message.await_count, 2)
            self.assertFalse(worker.done())
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
