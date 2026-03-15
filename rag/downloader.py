"""
downloader.py -- One-time model download + local cache for Android/Desktop.

This module intentionally does NOT support APK-bundled GGUF extraction.
The app logic is:
1) On first launch, download required models from Hugging Face.
2) Save them under app-private models/ storage.
3) On every later launch, reuse local files and skip download.
"""
from __future__ import annotations

import os
import shutil
import threading
from typing import Callable, Optional


# ------------------------------------------------------------------ #
#  Model catalog                                                      #
# ------------------------------------------------------------------ #

# Generation model (chat completion).
QWEN_MODEL: dict = {
    "label": "Qwen 2.5 1.5B Instruct Q4_K_M (~1.1 GB)",
    "repo_id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "size_mb": 1120,
}

# Embedding model (retrieval vectors).
NOMIC_MODEL: dict = {
    "label": "Nomic Embed Text v1.5 Q4_K_M (~80 MB)",
    "repo_id": "nomic-ai/nomic-embed-text-v1.5-GGUF",
    "filename": "nomic-embed-text-v1.5.Q4_K_M.gguf",
    "size_mb": 80,
}

MOBILE_MODELS: list[dict] = [QWEN_MODEL, NOMIC_MODEL]

_MB = 1_048_576
_MIN_VALID_BYTES: dict[str, int] = {
    QWEN_MODEL["filename"]: 100 * _MB,
    NOMIC_MODEL["filename"]: 10 * _MB,
}


# ------------------------------------------------------------------ #
#  Local destination                                                  #
# ------------------------------------------------------------------ #

def _models_dir() -> str:
    base = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))
    d = os.path.join(base, "models")
    os.makedirs(d, exist_ok=True)
    return d


def model_dest_path(filename: str) -> str:
    return os.path.join(_models_dir(), filename)


def _has_valid_file(path: str, min_bytes: int) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except Exception:
        return False


def is_downloaded(filename: str) -> bool:
    min_bytes = _MIN_VALID_BYTES.get(filename, 1 * _MB)
    return _has_valid_file(model_dest_path(filename), min_bytes=min_bytes)


# ------------------------------------------------------------------ #
#  Hugging Face helpers                                               #
# ------------------------------------------------------------------ #

def _get_hf_hub():
    try:
        from huggingface_hub import hf_hub_download
        return hf_hub_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is not installed.\n"
            "Install it with: pip install huggingface-hub"
        )


def _expected_bytes(repo_id: str, filename: str) -> int:
    """Return file size in bytes from HF metadata (without downloading)."""
    try:
        from huggingface_hub import get_hf_file_metadata, hf_hub_url

        url = hf_hub_url(repo_id=repo_id, filename=filename)
        meta = get_hf_file_metadata(url)
        return meta.size or 0
    except Exception:
        return 0


def _download_model_sync(
    repo_id: str,
    filename: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> tuple[bool, str]:
    """
    Blocking model download helper.
    Returns (success, destination_path_or_error).
    """
    dest = model_dest_path(filename)
    min_bytes = _MIN_VALID_BYTES.get(filename, 1 * _MB)

    if _has_valid_file(dest, min_bytes=min_bytes):
        if on_progress:
            on_progress(1.0, "Already downloaded.")
        return True, dest

    hf_hub_download = _get_hf_hub()

    if on_progress:
        on_progress(0.0, "Connecting to Hugging Face...")

    total_bytes = _expected_bytes(repo_id, filename)
    stop_poll = threading.Event()

    def _poller():
        # huggingface_hub often writes to .incomplete first.
        inc_path = dest + ".incomplete"
        while not stop_poll.wait(0.5):
            check = inc_path if os.path.isfile(inc_path) else dest
            if not os.path.isfile(check):
                continue
            done = os.path.getsize(check)
            if total_bytes > 0:
                frac = min(done / total_bytes, 0.99)
                mb_d = done / _MB
                mb_t = total_bytes / _MB
                if on_progress:
                    on_progress(frac, f"{mb_d:.0f} / {mb_t:.0f} MB")
            else:
                mb_d = done / _MB
                if on_progress:
                    on_progress(0.0, f"{mb_d:.0f} MB downloaded...")

    poll_thread = threading.Thread(target=_poller, daemon=True)
    poll_thread.start()

    try:
        kwargs: dict = {
            "repo_id": repo_id,
            "filename": filename,
            "local_dir": _models_dir(),
        }
        # Keep compatibility with older huggingface_hub versions.
        try:
            import inspect
            from huggingface_hub import hf_hub_download as _hfd

            if "local_dir_use_symlinks" in inspect.signature(_hfd).parameters:
                kwargs["local_dir_use_symlinks"] = False
        except Exception:
            pass

        cached = hf_hub_download(**kwargs)
        if os.path.abspath(cached) != os.path.abspath(dest):
            shutil.copy2(cached, dest)

        if not _has_valid_file(dest, min_bytes=min_bytes):
            return False, f"Downloaded file is invalid or too small: {filename}"

        if on_progress:
            on_progress(1.0, "Download complete.")
        return True, dest

    except Exception as exc:
        return False, f"Download failed: {exc}"
    finally:
        stop_poll.set()
        poll_thread.join(timeout=1)


# ------------------------------------------------------------------ #
#  Public download APIs                                               #
# ------------------------------------------------------------------ #

def download_model(
    repo_id: str,
    filename: str,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Download one GGUF asynchronously to models/ with progress callbacks.
    """
    def _run():
        ok, message = _download_model_sync(
            repo_id=repo_id,
            filename=filename,
            on_progress=on_progress,
        )
        if on_done:
            on_done(ok, message)

    threading.Thread(target=_run, daemon=True).start()


_AUTO_DL_LOCK = threading.Lock()
_AUTO_DL_RUNNING = False
_AUTO_DL_WAITERS: list[tuple[
    Optional[Callable[[float, str], None]],
    Optional[Callable[[bool, str], None]],
]] = []


def auto_download_default(
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Ensure Qwen + Nomic are available in models/ and cached for reuse.
    """
    def _notify_progress(frac: float, text: str) -> None:
        with _AUTO_DL_LOCK:
            waiters = list(_AUTO_DL_WAITERS)
        for progress_cb, _ in waiters:
            if progress_cb:
                progress_cb(frac, text)

    def _notify_done(ok: bool, msg: str) -> None:
        global _AUTO_DL_RUNNING
        with _AUTO_DL_LOCK:
            waiters = list(_AUTO_DL_WAITERS)
            _AUTO_DL_WAITERS.clear()
            _AUTO_DL_RUNNING = False
        for _, done_cb in waiters:
            if done_cb:
                done_cb(ok, msg)

    qwen_dest = model_dest_path(QWEN_MODEL["filename"])
    nomic_dest = model_dest_path(NOMIC_MODEL["filename"])
    qwen_ok = _has_valid_file(qwen_dest, _MIN_VALID_BYTES[QWEN_MODEL["filename"]])
    nomic_ok = _has_valid_file(nomic_dest, _MIN_VALID_BYTES[NOMIC_MODEL["filename"]])

    if qwen_ok and nomic_ok:
        if on_progress:
            on_progress(1.0, "All models ready (cached).")
        if on_done:
            on_done(True, "All models ready (cached).")
        return

    start_worker = False
    with _AUTO_DL_LOCK:
        _AUTO_DL_WAITERS.append((on_progress, on_done))
        global _AUTO_DL_RUNNING
        if not _AUTO_DL_RUNNING:
            _AUTO_DL_RUNNING = True
            start_worker = True

    if not start_worker:
        return

    def _run():
        # Stage 1: Qwen download (70% of progress).
        if _has_valid_file(qwen_dest, _MIN_VALID_BYTES[QWEN_MODEL["filename"]]):
            _notify_progress(0.70, "Qwen model already cached.")
        else:
            def _qwen_progress(frac: float, text: str) -> None:
                _notify_progress(frac * 0.70, f"Downloading Qwen: {text}")

            ok, msg = _download_model_sync(
                repo_id=QWEN_MODEL["repo_id"],
                filename=QWEN_MODEL["filename"],
                on_progress=_qwen_progress,
            )
            if not ok:
                _notify_done(False, msg)
                return

        # Stage 2: Nomic download (30% of progress).
        if _has_valid_file(nomic_dest, _MIN_VALID_BYTES[NOMIC_MODEL["filename"]]):
            _notify_progress(1.0, "All models ready.")
            _notify_done(True, "All models ready.")
            return

        def _nomic_progress(frac: float, text: str) -> None:
            _notify_progress(0.70 + (frac * 0.30), f"Downloading Nomic: {text}")

        ok, msg = _download_model_sync(
            repo_id=NOMIC_MODEL["repo_id"],
            filename=NOMIC_MODEL["filename"],
            on_progress=_nomic_progress,
        )
        if not ok:
            _notify_done(False, msg)
            return

        _notify_progress(1.0, "All models ready.")
        _notify_done(True, "All models ready.")

    threading.Thread(target=_run, daemon=True).start()
