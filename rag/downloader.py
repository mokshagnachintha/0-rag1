"""
downloader.py - Download and cache GGUF models from Hugging Face.

This module now follows a download-only bootstrap flow:
  * No APK model extraction
  * Models are downloaded once on first launch
  * Bootstrap state is recorded in models/bootstrap_state.json
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional


# ------------------------------------------------------------------ #
#  Model manifest (pinned sources)                                   #
# ------------------------------------------------------------------ #

QWEN_MODEL: dict = {
    "id": "qwen",
    "label": "Qwen 2.5 1.5B Instruct Compressed (~1.12 GB)",
    "repo_id": "cracker0935/Compressed_RAG_Models",
    "filename": "qwen2.5-1.5b-instruct-compressed.gguf",
    "revision": "main",
    "size_mb": 1120,
    "min_bytes": 500 * 1024 * 1024,
    "url": "https://huggingface.co/cracker0935/Compressed_RAG_Models/resolve/main/qwen2.5-1.5b-instruct-compressed.gguf",
}


NOMIC_MODEL: dict = {
    "id": "nomic",
    "label": "Nomic Embed Text v1.5 Compressed (~84 MB)",
    "repo_id": "cracker0935/Compressed_RAG_Models",
    "filename": "nomic-embed-text-v1.5-compressed.gguf",
    "revision": "main",
    "size_mb": 84,
    "min_bytes": 30 * 1024 * 1024,
    "url": "https://huggingface.co/cracker0935/Compressed_RAG_Models/resolve/main/nomic-embed-text-v1.5-compressed.gguf",
}

MOBILE_MODELS: list[dict] = [QWEN_MODEL, NOMIC_MODEL]


# ------------------------------------------------------------------ #
#  Paths and bootstrap state                                         #
# ------------------------------------------------------------------ #

_BOOTSTRAP_FILE = "bootstrap_state.json"
_BOOTSTRAP_SCHEMA = 1


def _models_dir() -> str:
    base = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))
    dest = os.path.join(base, "models")
    os.makedirs(dest, exist_ok=True)
    return dest


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name, "")
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def model_dest_path(filename: str) -> str:
    return os.path.join(_models_dir(), filename)


def _bootstrap_state_path() -> str:
    return os.path.join(_models_dir(), _BOOTSTRAP_FILE)


def _manifest_payload() -> dict:
    return {
        "schema": _BOOTSTRAP_SCHEMA,
        "models": [
            {
                "repo_id": m["repo_id"],
                "filename": m["filename"],
                "revision": m.get("revision", "main"),
            }
            for m in MOBILE_MODELS
        ],
    }


def _manifest_hash() -> str:
    payload = json.dumps(_manifest_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_bootstrap_state() -> dict:
    path = _bootstrap_state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_bootstrap_state() -> None:
    state = {
        "schema": _BOOTSTRAP_SCHEMA,
        "manifest_hash": _manifest_hash(),
        "completed_at": int(time.time()),
        "models": [
            {
                "filename": m["filename"],
                "repo_id": m["repo_id"],
                "revision": m.get("revision", "main"),
                "size_bytes": os.path.getsize(model_dest_path(m["filename"]))
                if os.path.isfile(model_dest_path(m["filename"]))
                else 0,
            }
            for m in MOBILE_MODELS
        ],
    }
    tmp = _bootstrap_state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, _bootstrap_state_path())


def _is_model_file_ready(meta: dict) -> bool:
    path = model_dest_path(meta["filename"])
    min_bytes = int(meta.get("min_bytes", 1 * 1024 * 1024))
    return os.path.isfile(path) and os.path.getsize(path) >= min_bytes


def _is_bootstrap_complete() -> bool:
    state = _load_bootstrap_state()
    if not state:
        return False
    if state.get("schema") != _BOOTSTRAP_SCHEMA:
        return False
    if state.get("manifest_hash") != _manifest_hash():
        return False
    return all(_is_model_file_ready(meta) for meta in MOBILE_MODELS)


def is_downloaded(filename: str) -> bool:
    for meta in MOBILE_MODELS:
        if meta["filename"] == filename:
            return _is_model_file_ready(meta)
    path = model_dest_path(filename)
    return os.path.isfile(path) and os.path.getsize(path) > 0


# ------------------------------------------------------------------ #
#  Download helpers                                                  #
# ------------------------------------------------------------------ #

def _get_hf_hub():
    try:
        from huggingface_hub import hf_hub_download
        return hf_hub_download
    except ImportError:
        return None


def _hf_resolve_url(repo_id: str, filename: str, revision: str) -> str:
    # Public, unauthenticated download URL
    return f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}?download=true"


def _tls_context() -> ssl.SSLContext:
    """
    Build a TLS context that prefers certifi's CA bundle (reliable on Android),
    then falls back to system defaults.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _download_via_http(
    repo_id: str,
    filename: str,
    revision: str,
    dest: str,
    expected_size_mb: int = 0,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> None:
    """
    Fallback downloader when huggingface_hub is unavailable on-device.
    Supports best-effort resume via HTTP Range requests.
    """
    url = _hf_resolve_url(repo_id, filename, revision)
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tls_ctx = _tls_context()

    start = 0
    if os.path.isfile(part):
        try:
            start = os.path.getsize(part)
        except Exception:
            start = 0

    headers = {"User-Agent": "O-RAG/1.0"}
    if start > 0:
        headers["Range"] = f"bytes={start}-"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30, context=tls_ctx) as resp:
        status = getattr(resp, "status", 200)
        content_len = int(resp.headers.get("Content-Length", "0") or "0")

        # If server ignored Range and returned full content, restart part file.
        if start > 0 and status != 206:
            start = 0
            try:
                os.remove(part)
            except Exception:
                pass

        total = 0
        if status == 206 and content_len > 0:
            total = start + content_len
        elif content_len > 0:
            total = content_len
        elif expected_size_mb > 0:
            total = int(expected_size_mb * 1_048_576)

        mode = "ab" if start > 0 else "wb"
        done = start
        with open(part, mode) as f:
            while True:
                chunk = resp.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)

                if on_progress:
                    if total > 0:
                        frac = min(done / total, 0.99)
                        on_progress(frac, f"{done/1_048_576:.0f} / {total/1_048_576:.0f} MB")
                    else:
                        on_progress(0.05, f"{done/1_048_576:.0f} MB downloaded...")

    os.replace(part, dest)


def download_model(
    repo_id: str,
    filename: str,
    revision: str = "main",
    min_bytes: int = 1,
    expected_size_mb: int = 0,
    force_download: bool = False,
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Download a GGUF file from Hugging Face to the local models/ folder.
    Runs in a background thread.
    """

    def _run():
        dest = model_dest_path(filename)

        if (
            not force_download
            and os.path.isfile(dest)
            and os.path.getsize(dest) >= max(1, int(min_bytes))
        ):
            if on_progress:
                on_progress(1.0, "Already downloaded.")
            if on_done:
                on_done(True, dest)
            return

        hf_hub_download = _get_hf_hub()

        if on_progress:
            on_progress(0.02, "Connecting to Hugging Face...")

        if hf_hub_download is None:
            try:
                _download_via_http(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    dest=dest,
                    expected_size_mb=expected_size_mb,
                    on_progress=on_progress,
                )
                if on_progress:
                    on_progress(1.0, "Download complete.")
                if on_done:
                    on_done(True, dest)
            except urllib.error.URLError as exc:
                if on_done:
                    on_done(False, f"Download failed (network): {exc}")
            except Exception as exc:
                if on_done:
                    on_done(False, f"Download failed: {exc}")
            return

        # Use local manifest size for progress tracking; avoids extra metadata
        # calls that can stall/fail on some Android networks.
        total_bytes = int(expected_size_mb * 1_048_576) if expected_size_mb > 0 else 0
        stop_poll = threading.Event()

        def _poller():
            incomplete_candidates = [
                dest + ".incomplete",
                dest + ".part",
            ]
            pulse = 0.02
            while not stop_poll.wait(0.5):
                check = dest
                for candidate in incomplete_candidates:
                    if os.path.isfile(candidate):
                        check = candidate
                        break

                if os.path.isfile(check):
                    done = os.path.getsize(check)
                    if total_bytes:
                        frac = min(done / total_bytes, 0.99)
                        mb_done = done / 1_048_576
                        mb_total = total_bytes / 1_048_576
                        if on_progress:
                            on_progress(frac, f"{mb_done:.0f} / {mb_total:.0f} MB")
                    elif on_progress:
                        mb_done = done / 1_048_576
                        on_progress(0.0, f"{mb_done:.0f} MB downloaded...")
                elif on_progress:
                    pulse = min(pulse + 0.005, 0.08)
                    on_progress(pulse, "Preparing download...")

        poll_thread = threading.Thread(target=_poller, daemon=True)
        poll_thread.start()

        try:
            kwargs: dict = {
                "repo_id": repo_id,
                "filename": filename,
                "revision": revision,
                "local_dir": _models_dir(),
            }

            try:
                import inspect
                from huggingface_hub import hf_hub_download as _hfd

                sig = inspect.signature(_hfd).parameters
                if "local_dir_use_symlinks" in sig:
                    kwargs["local_dir_use_symlinks"] = False
                if force_download and "force_download" in sig:
                    kwargs["force_download"] = True
            except Exception:
                pass

            cached = hf_hub_download(**kwargs)

            stop_poll.set()
            poll_thread.join(timeout=1)

            if os.path.abspath(cached) != os.path.abspath(dest):
                shutil.copy2(cached, dest)

            if on_progress:
                on_progress(1.0, "Download complete.")
            if on_done:
                on_done(True, dest)

        except Exception as exc:
            stop_poll.set()
            poll_thread.join(timeout=1)
            if on_done:
                on_done(False, f"Download failed: {exc}")

    threading.Thread(target=_run, daemon=True).start()


# ------------------------------------------------------------------ #
#  One-time bootstrap                                                #
# ------------------------------------------------------------------ #

def auto_download_default(
    on_progress: Optional[Callable[[float, str], None]] = None,
    on_done: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Ensure both Qwen + Nomic are present for offline use.

    Rules:
      1) If bootstrap state matches current manifest and files are valid -> skip network
      2) If manifest changed, re-sync all models from Hugging Face
      3) Otherwise download any missing models from Hugging Face
      4) Save bootstrap_state.json when complete
    """

    total = len(MOBILE_MODELS)

    def _emit(index: int, frac: float, text: str) -> None:
        if not on_progress:
            return
        frac = max(0.0, min(1.0, frac))
        overall = (index + frac) / total
        on_progress(overall, text)

    force_every_run = _env_truthy("ORAG_FORCE_BOOTSTRAP_DOWNLOAD")
    force_network = _env_truthy("ORAG_FORCE_NETWORK_MODEL_DOWNLOAD")

    if _is_bootstrap_complete() and not force_every_run:
        if on_progress:
            on_progress(1.0, "Offline ready. Using cached AI models.")
        if on_done:
            on_done(True, "All models ready: cached and offline.")
        return

    previous_state = _load_bootstrap_state()
    manifest_changed = bool(previous_state) and previous_state.get("manifest_hash") != _manifest_hash()

    def _ensure_model(index: int) -> None:
        if index >= total:
            try:
                _save_bootstrap_state()
            except Exception as exc:
                if on_done:
                    on_done(False, f"Failed to write bootstrap state: {exc}")
                return

            if on_progress:
                on_progress(1.0, "Offline ready. AI models cached on device.")
            if on_done:
                on_done(True, "All models ready: Qwen + Nomic")
            return

        meta = MOBILE_MODELS[index]
        label = meta["label"].split("(")[0].strip()

        if _is_model_file_ready(meta) and not manifest_changed and not force_every_run:
            _emit(index, 1.0, f"{label} already cached.")
            _ensure_model(index + 1)
            return

        if force_every_run:
            try:
                stale = model_dest_path(meta["filename"])
                if os.path.isfile(stale):
                    os.remove(stale)
            except Exception:
                pass

        if force_every_run:
            _emit(index, 0.0, f"Downloading {label} (dev force mode)...")
        else:
            _emit(index, 0.0, f"Downloading {label} (first launch only)...")

        def _on_progress(frac: float, text: str) -> None:
            _emit(index, frac, f"{label}: {text}")

        def _on_done(success: bool, message: str) -> None:
            if not success:
                if on_done:
                    on_done(False, message)
                return

            if not _is_model_file_ready(meta):
                if on_done:
                    on_done(False, f"Download incomplete: {meta['filename']}")
                return

            _ensure_model(index + 1)

        download_model(
            repo_id=meta["repo_id"],
            filename=meta["filename"],
            revision=meta.get("revision", "main"),
            min_bytes=int(meta.get("min_bytes", 1)),
            expected_size_mb=int(meta.get("size_mb", 0)),
            force_download=(manifest_changed or force_every_run or force_network),
            on_progress=_on_progress,
            on_done=_on_done,
        )

    _ensure_model(0)

