from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from astrbot_plugin_wechat_sticker_receiver.native_events import private_session, sticker_timestamp
from astrbot_plugin_wechat_sticker_receiver.probe_native import ProbeError, endpoint, event_candidates
from astrbot_plugin_wechat_sticker_receiver.render_sticker import render


class FeasibilityTests(unittest.TestCase):
    def test_private_session_matches_adapter_encoding(self):
        self.assertEqual(private_session("test/a", "peer:b"), "test%2Fa|private|peer%3Ab")

    def test_only_native_sticker_types_with_timezone_are_accepted(self):
        raw = {"type": 47, "createdAt": "2026-11-22T01:00:12Z"}
        timestamp = sticker_timestamp(raw)
        self.assertIsInstance(timestamp, int)
        self.assertEqual(sticker_timestamp({**raw, "type": 49, "appMessageType": 8}), timestamp)
        self.assertIsNone(sticker_timestamp({**raw, "type": 49, "appMessageType": 57}))
        self.assertIsNone(sticker_timestamp({**raw, "type": 1}))
        self.assertIsNone(sticker_timestamp({**raw, "createdAt": "2026-11-22T01:00:12"}))

    def test_native_path_is_loopback_and_account_is_encoded(self):
        self.assertEqual(
            endpoint("http://127.0.0.1:6174/", "test/a"),
            "http://127.0.0.1:6174/v1/accounts/test%2Fa",
        )
        for origin in ("http://example.com", "http://localhost@localhost", "http://localhost/v1"):
            with self.subTest(origin=origin), self.assertRaises(ProbeError):
                endpoint(origin, "test")

    def test_sse_candidate_requires_live_message_in_selected_thread(self):
        data = {"messageId": "42", "origin": "live", "threadId": "peer"}
        self.assertEqual(event_candidates({"kind": "message.committed", "data": data}, "peer"), "42")
        self.assertIsNone(event_candidates({"kind": "media.ready", "data": data}, "peer"))
        self.assertIsNone(event_candidates({"kind": "message.committed", "data": data}, "other"))
        self.assertIsNone(
            event_candidates({"kind": "message.committed", "data": {**data, "origin": "history"}}, "peer")
        )

    def test_static_png_preserves_transparency(self):
        original = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        out = BytesIO()
        original.save(out, "PNG")
        visual = render(out.getvalue())
        self.assertEqual(visual.sample_count, 1)
        self.assertFalse(visual.preview)
        with Image.open(BytesIO(visual.png)) as png:
            self.assertEqual(png.getpixel((0, 0))[3], 0)

    def test_gif_frames_follow_reading_order_and_preview_has_only_one_frame(self):
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        frames = [Image.new("RGB", (16, 16), color) for color in colors]
        out = BytesIO()
        frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=100)
        visual = render(out.getvalue())
        self.assertEqual(visual.sample_count, 4)
        with Image.open(BytesIO(visual.png)) as png:
            right, bottom = png.width - 1, png.height - 1
            self.assertEqual(
                [png.getpixel(position)[:3] for position in ((0, 0), (right, 0), (0, bottom), (right, bottom))],
                colors,
            )
        preview = render(out.getvalue(), preview=True)
        self.assertEqual(preview.sample_count, 1)
        self.assertTrue(preview.preview)

    def test_invalid_media_is_rejected(self):
        with self.assertRaises(OSError):
            render(b"This is not a sticker")
