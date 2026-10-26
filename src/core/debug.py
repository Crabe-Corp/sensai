"""Centralized debug and logging system for Sensai."""
import os

_DEBUG_ENABLED: bool = os.getenv("SENSAI_DEBUG", "").lower() in ("1", "true", "yes")


def set_debug(enabled: bool) -> None:
    """Set the global debug mode flag.
            PARAMS: - enabled - BOOL: True to enable debug messages, False to silence
            RETURN: None"""
    global _DEBUG_ENABLED
    _DEBUG_ENABLED = bool(enabled)


def is_debug() -> bool:
    """Check if debug mode is currently enabled.
            PARAMS: None
            RETURN: bool indicating if debug output is active"""
    return _DEBUG_ENABLED


def debug_print(*args, **kwargs) -> None:
    """Print message to stdout only when debug mode is enabled.
            PARAMS: - args, kwargs - ANY: arguments passed directly to built-in print
            RETURN: None"""
    if _DEBUG_ENABLED:
        print(*args, **kwargs)

