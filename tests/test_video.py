"""H.264 解码与屏幕会话回调的测试。"""

import unittest

from app.core import video


def encode_frames(count=4, width=64, height=48):
    """用 PyAV 现场编一段 H.264 码流，返回 Annex-B 字节。

    Args:
        count: 帧数。
        width: 画面宽度。
        height: 画面高度。

    Returns:
        bytes: 编码后的码流。
    """
    from fractions import Fraction

    import av
    import numpy as np

    context = av.CodecContext.create("libx264", "w")
    context.width = width
    context.height = height
    context.pix_fmt = "yuv420p"
    context.time_base = Fraction(1, 25)
    context.framerate = Fraction(25, 1)
    # 用最快的预设与零延迟参数，避免编码消耗测试时间。
    context.options = {"preset": "ultrafast", "tune": "zerolatency"}
    chunks = []
    for index in range(count):
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[:, :, 1] = 40 * index
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
        chunks.extend(bytes(packet) for packet in context.encode(frame))
    chunks.extend(bytes(packet) for packet in context.encode(None))
    return b"".join(chunks)


@unittest.skipUnless(video.available(), "未安装 PyAV")
class H264DecoderTests(unittest.TestCase):
    """解码器要能把码流还原成 RGB 位图。"""

    def test_decode_returns_rgb_frames(self):
        decoder = video.H264Decoder()
        frames = decoder.decode(encode_frames())
        self.assertTrue(frames)
        width, height, pixels = frames[0]
        self.assertEqual((width, height), (64, 48))
        self.assertEqual(len(pixels), 64 * 48 * 3)
        self.assertGreater(decoder.frames, 0)

    def test_decode_ignores_empty_payload(self):
        decoder = video.H264Decoder()
        self.assertEqual(decoder.decode(b""), [])
        self.assertEqual(decoder.frames, 0)

    def test_decode_survives_broken_stream(self):
        decoder = video.H264Decoder()
        decoder.decode(b"\x00\x00\x00\x01\x65\x88")
        # 坏码流不应该抛异常，后面的好码流还要能继续解。
        self.assertTrue(decoder.decode(encode_frames(2)))

    def test_reset_drops_context(self):
        decoder = video.H264Decoder()
        decoder.decode(encode_frames(2))
        decoder.reset()
        self.assertIsNone(decoder._context)
        self.assertTrue(decoder.decode(encode_frames(2)))


class VideoAvailabilityTests(unittest.TestCase):
    """可用性检查不能受解码器状态影响。"""

    def test_available_matches_import_result(self):
        try:
            import av  # noqa: F401
        except ImportError:
            self.assertFalse(video.available())
        else:
            self.assertTrue(video.available())
