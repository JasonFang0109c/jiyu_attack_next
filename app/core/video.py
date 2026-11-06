"""H.264 解码：把学生端推来的 Annex-B 码流解成 RGB 位图。

学生端每条桌面记录是一段 H.264 Annex-B 码流，可能只有一帧，也可能是接在
上一条之后的续帧，因此解析器与解码上下文都要跨记录保留。解码本身交给
PyAV（FFmpeg 的 Python 绑定），这里只负责把它包装成简单的接口。
"""


def available():
    """PyAV 是否可用。

    Returns:
        bool: 能导入 ``av`` 时为真。
    """
    try:
        import av  # noqa: F401
    except ImportError:
        return False
    return True


class H264Decoder:
    """增量解码一条持续的 H.264 码流。

    Attributes:
        frames: 已成功解出的帧数。
        errors: 解码出错的次数。
    """

    def __init__(self):
        self._context = None
        self.frames = 0
        self.errors = 0

    def _ensure_context(self):
        """按需创建解码上下文，缺依赖时给出可读的异常。"""
        if self._context is not None:
            return self._context
        try:
            import av
        except ImportError as error:
            raise RuntimeError("H.264 解码需要 PyAV，请先安装依赖") from error
        self._context = av.CodecContext.create("h264", "r")
        return self._context

    def _feed(self, data):
        """把一段码流喂给解码器，失败时抛 PyAV 的异常。"""
        context = self._ensure_context()
        frames = []
        for packet in context.parse(data):
            for frame in context.decode(packet):
                array = frame.to_ndarray(format="rgb24")
                frames.append((array.shape[1], array.shape[0], array.tobytes()))
        return frames

    def decode(self, data):
        """解一段码流。

        Args:
            data: Annex-B 格式的码流字节。

        Returns:
            list: 每项是 ``(width, height, rgb_bytes)``，没有可显示的帧时为空。

        Raises:
            RuntimeError: 运行环境缺少 PyAV。
        """
        if not data:
            return []
        import av

        for attempt in range(2):
            try:
                frames = self._feed(data)
            except (ValueError, av.error.FFmpegError):
                # 坏数据会污染解码状态，重建上下文后重试一次；第二次仍失败
                # 说明这段码流本身不可解，丢掉即可，不影响后续记录。
                self.errors += 1
                self.reset()
                if attempt:
                    return []
                continue
            self.frames += len(frames)
            return frames
        return []

    def reset(self):
        """丢掉解码上下文，下一段码流从关键帧重新开始。"""
        self._context = None
