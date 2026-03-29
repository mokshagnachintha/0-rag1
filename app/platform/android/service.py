"""
Android platform helpers for foreground service lifecycle.
"""
from __future__ import annotations

from app.config import SERVICE_MESSAGE, SERVICE_TITLE


def is_android_runtime() -> bool:
    try:
        import os

        return bool(os.environ.get("ANDROID_PRIVATE"))
    except Exception:
        return False


def start_foreground_service() -> bool:
    """Start the app foreground service if Android APIs are available."""
    try:
        from android import AndroidService  # type: ignore

        svc = AndroidService(SERVICE_TITLE, SERVICE_MESSAGE)
        svc.start("start")
        print("[platform] Android foreground service started.")
        return True
    except Exception as exc:
        print(f"[platform] Service start skipped: {exc}")
        return False
