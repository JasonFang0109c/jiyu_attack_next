"""兼容层异常类型。"""


class CompatibilityError(Exception):
    """表示兼容契约未满足。"""


class UnsupportedBackendError(CompatibilityError):
    """表示当前后端不支持所请求的操作。"""


class BackendOperationError(CompatibilityError):
    """表示后端操作执行失败。"""
