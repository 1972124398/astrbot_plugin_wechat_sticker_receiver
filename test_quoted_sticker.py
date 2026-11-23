"""Quote source validation and authenticated Native media integration tests."""

import copy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import aiohttp
from aiohttp import web
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrbot_plugin_wechat_sticker_receiver.probe_native import MediaPending, ProbeError, inspect_media
from astrbot_plugin_wechat_sticker_receiver.quoted_sticker import (
    check_original, check_quote, quoted_sticker, recheck_original, resolve_source,
)


def reply(**changes):
    raw = {
        "id": "reply/1", "accountId": "a", "threadId": "peer", "senderId": "peer",
        "serverId": "901", "direction": "incoming", "type": 49, "appMessageType": 57,
        "body": "这个表情是什么意思？", "recall": None,
        "quote": {
            "serverId": "900", "senderId": "peer", "type": 47,
            "state": "embedded", "embeddedSticker": True,
        },
    }
    raw.update(changes)
    return raw


def original(**changes):
    raw = {
        "id": "old/1", "accountId": "a", "threadId": "peer", "senderId": "peer",
        "serverId": "900", "direction": "incoming", "type": 47, "recall": None,
    }
    raw.update(changes)
    return raw


class QuoteValidationTests(unittest.TestCase):
    def test_native_and_shared_quotes(self):
        for kind, subtype in ((47, None), (49, 8)):
            raw = reply()
            raw["quote"].update(type=kind, appMessageType=subtype)
            self.assertTrue(quoted_sticker(raw))
            check_original(original(type=kind, appMessageType=subtype), raw, "old/1")

    def test_non_sticker_and_unavailable_quotes_are_rejected(self):
        for changes in (
            {"type": 3}, {"type": 1}, {"type": 49, "appMessageType": 6},
            {"embeddedSticker": False}, {"state": "recalled"}, {"state": "expired"},
            {"state": "unsupported"}, {"state": "missing", "serverId": ""},
            {"state": "missing", "senderId": None},
        ):
            with self.subTest(changes=changes):
                raw = reply()
                raw["quote"].update(changes)
                self.assertFalse(quoted_sticker(raw))
        self.assertFalse(quoted_sticker(reply(recall={})))
        self.assertFalse(quoted_sticker(reply(type=1)))
        self.assertFalse(quoted_sticker(reply(quote=None)))

    def test_original_identity_and_recall_checks(self):
        for changes in (
            {"id": "other"}, {"accountId": "b"}, {"threadId": "other"},
            {"senderId": "stranger"}, {"serverId": "902"}, {"type": 3}, {"recall": {}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ProbeError):
                check_original(original(**changes), reply(), "old/1")

    def test_parent_identity_and_quote_are_rechecked(self):
        raw = reply()
        for changes in (
            {"accountId": "b"}, {"threadId": "other"}, {"id": "other"},
            {"senderId": "other"}, {"serverId": "other"}, {"direction": "outgoing"},
            {"recall": {}}, {"quote": {**raw["quote"], "serverId": "other"}},
            {"quote": {**raw["quote"], "state": "recalled"}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ProbeError):
                check_quote({**raw, **changes}, raw)

    def test_quotes_can_reference_own_sent_sticker(self):
        raw = reply()
        raw["quote"]["senderId"] = "self"
        check_original(original(senderId="self", direction="outgoing"), raw, "old/1")


class NativeQuoteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.raw = reply()
        self.saved = original()
        self.lookups = []
        self.items = [self.saved]
        self.assets = []
        out = BytesIO()
        Image.new("RGBA", (12, 12), "red").save(out, "PNG")
        self.blob = out.getvalue()

        async def native(request):
            self.lookups.append((request.path, dict(request.query)))
            path = request.path
            if path.endswith("/threads/peer/messages"):
                return web.json_response({"items": self.items})
            if path.endswith("/messages/old/1"):
                return web.json_response(self.saved)
            if path.endswith("/messages/reply/1"):
                return web.json_response(self.raw)
            if path.endswith("/media"):
                return web.json_response({"items": self.assets})
            if "/media/" in path and path.endswith("/content"):
                return web.Response(body=self.blob)
            raise web.HTTPNotFound()

        app = web.Application()
        app.router.add_get("/{tail:.*}", native)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{port}/v1/accounts/a"
        self.client = aiohttp.ClientSession(trust_env=False)

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()

    def asset(self, **changes):
        asset = {
            "id": "asset/1", "accountId": "a", "messageId": "reply/1", "source": "quote",
            "kind": "sticker", "state": "available", "variant": "original",
            "contentType": "image/png", "byteLength": len(self.blob),
            "sha256": sha256(self.blob).hexdigest(),
        }
        asset.update(changes)
        return asset

    async def media(self, **kwargs):
        return await inspect_media(
            self.client, self.base, self.base + "/messages/reply%2F1", "a", "reply/1",
            report=False, **kwargs,
        )

    async def test_embedded_quote_uses_reply_id_without_original_lookup(self):
        self.assertEqual(await resolve_source(self.client, self.base, self.raw), ("reply/1", True))
        self.assertEqual(self.lookups, [])
        self.assets = [self.asset()]
        self.assertEqual(await self.media(quoted=True), (self.blob, False))
        self.assertEqual(self.lookups[0][0], "/v1/accounts/a/messages/reply/1/media")

    async def test_quote_and_direct_media_do_not_cross_sources(self):
        self.assets = [self.asset()]
        with self.assertRaises(ProbeError):
            await self.media()
        self.assets = [self.asset(source="message")]
        with self.assertRaises(ProbeError):
            await self.media(quoted=True)
        self.assertEqual(await self.media(), (self.blob, False))

    async def test_legacy_unlabelled_quote_asset_is_supported(self):
        self.assets = [self.asset(source=None)]
        self.assertEqual(await self.media(quoted=True), (self.blob, False))

    async def test_quote_asset_requires_matching_account_parent_and_kind(self):
        for changes in ({"accountId": "b"}, {"messageId": "old/1"}, {"kind": "image"}):
            with self.subTest(changes=changes):
                self.assets = [self.asset(**changes)]
                with self.assertRaises(ProbeError):
                    await self.media(quoted=True)

    async def test_pending_quote_asset_requests_transfer(self):
        self.assets = [self.asset(state="pending")]
        with self.assertRaises(MediaPending) as caught:
            await self.media(quoted=True)
        self.assertEqual(caught.exception.asset_id, "asset/1")

    async def test_wxgf_quote_uses_verified_preview(self):
        preview = {
            "sourceSha256": "a" * 64, "byteLength": len(self.blob),
            "sha256": sha256(self.blob).hexdigest(),
        }
        self.assets = [self.asset(contentType="image/x-wxgf", sha256="a" * 64, preview=preview)]
        self.assertEqual(await self.media(quoted=True), (self.blob, True))
        self.assertEqual(self.lookups[-1][1], {"representation": "preview"})

    async def test_missing_quote_uses_bounded_same_chat_lookup(self):
        self.raw["quote"].update(state="missing", embeddedSticker=False)
        self.assertEqual(await resolve_source(self.client, self.base, self.raw), ("old/1", False))
        self.assertEqual(self.lookups[0], ("/v1/accounts/a/threads/peer/messages", {"limit": "50"}))

    async def test_missing_original_wrong_chat_or_recalled_is_rejected(self):
        self.raw["quote"]["state"] = "missing"
        for changes in ({"threadId": "other"}, {"senderId": "other"}, {"recall": {}}):
            with self.subTest(changes=changes):
                self.saved = original(**changes)
                self.items = [self.saved]
                with self.assertRaises(ProbeError):
                    await resolve_source(self.client, self.base, self.raw)

    async def test_missing_or_ambiguous_original_is_rejected(self):
        self.raw["quote"]["state"] = "missing"
        for items in ([], [self.saved, copy.deepcopy(self.saved)]):
            self.items = items
            with self.assertRaises(ProbeError):
                await resolve_source(self.client, self.base, self.raw)

    async def test_original_recall_after_download_is_rejected(self):
        self.raw["quote"]["state"] = "missing"
        source_id, _ = await resolve_source(self.client, self.base, self.raw)
        self.saved["recall"] = {}
        with self.assertRaises(ProbeError):
            await recheck_original(self.client, self.base, self.raw, source_id)

    async def test_cached_original_is_verified_without_history_lookup(self):
        self.raw["quote"]["state"] = "missing"
        state = SimpleNamespace(
            is_recalled=lambda *args: False, find_message_id=lambda *args: "old/1",
            message_status=lambda message_id: "ignored",
        )
        self.assertEqual(await resolve_source(self.client, self.base, self.raw, state), ("old/1", False))
        self.assertEqual(len(self.lookups), 1)
        self.assertEqual(self.lookups[0][0], "/v1/accounts/a/messages/old/1")

    async def test_local_recall_blocks_embedded_quote_without_downloading(self):
        state = SimpleNamespace(is_recalled=lambda *args: True)
        with self.assertRaises(ProbeError):
            await resolve_source(self.client, self.base, self.raw, state)
        self.assertEqual(self.lookups, [])

    async def test_local_original_recall_blocks_missing_quote(self):
        self.raw["quote"]["state"] = "missing"
        state = SimpleNamespace(
            is_recalled=lambda *args: False, find_message_id=lambda *args: "old/1",
            message_status=lambda message_id: "recalled",
        )
        with self.assertRaises(ProbeError):
            await resolve_source(self.client, self.base, self.raw, state)
        self.assertEqual(self.lookups, [])
