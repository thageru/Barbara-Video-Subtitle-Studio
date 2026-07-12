from __future__ import annotations

import ctypes
import platform
from ctypes import c_bool, c_char_p, c_long, c_void_p, create_string_buffer
from functools import lru_cache

from .processor import ProcessingError

_UTF8 = 0x08000100


@lru_cache(maxsize=1)
def _opencc_converter():
    try:
        from opencc import OpenCC  # type: ignore
    except Exception:
        return None
    return OpenCC("t2s")


def to_simplified_chinese(text: str) -> str:
    if not text:
        return text

    converter = _opencc_converter()
    if converter is not None:
        return converter.convert(text)

    if platform.system() == "Darwin":
        return _corefoundation_to_simplified(text)

    raise ProcessingError(
        "Simplified Chinese output requires opencc-python-reimplemented. "
        "Install it once, then the tool can run offline from the local environment."
    )


def _corefoundation_to_simplified(text: str) -> str:
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, ctypes.c_uint32]
    cf.CFStringCreateWithCString.restype = c_void_p
    cf.CFStringCreateMutableCopy.argtypes = [c_void_p, c_long, c_void_p]
    cf.CFStringCreateMutableCopy.restype = c_void_p
    cf.CFStringTransform.argtypes = [c_void_p, c_void_p, c_void_p, c_bool]
    cf.CFStringTransform.restype = c_bool
    cf.CFStringGetLength.argtypes = [c_void_p]
    cf.CFStringGetLength.restype = c_long
    cf.CFStringGetMaximumSizeForEncoding.argtypes = [c_long, ctypes.c_uint32]
    cf.CFStringGetMaximumSizeForEncoding.restype = c_long
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, ctypes.c_uint32]
    cf.CFStringGetCString.restype = c_bool
    cf.CFRelease.argtypes = [c_void_p]

    source = cf.CFStringCreateWithCString(None, text.encode("utf-8"), _UTF8)
    transform = cf.CFStringCreateWithCString(None, b"Traditional-Simplified", _UTF8)
    mutable = None
    try:
        mutable = cf.CFStringCreateMutableCopy(None, 0, source)
        if not cf.CFStringTransform(mutable, None, transform, False):
            raise ProcessingError("CoreFoundation failed to convert Traditional Chinese to Simplified Chinese")
        length = cf.CFStringGetLength(mutable)
        size = cf.CFStringGetMaximumSizeForEncoding(length, _UTF8) + 1
        buffer = create_string_buffer(size)
        if not cf.CFStringGetCString(mutable, buffer, size, _UTF8):
            raise ProcessingError("CoreFoundation failed to encode converted text as UTF-8")
        return buffer.value.decode("utf-8")
    finally:
        if mutable:
            cf.CFRelease(mutable)
        if source:
            cf.CFRelease(source)
        if transform:
            cf.CFRelease(transform)
