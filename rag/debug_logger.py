from __future__ import annotations
import os
import threading
import time
from typing import Dict, List

_LOCK = threading.Lock()
_DEBUG_FILE = "debug_events.log"

_SOURCE_GROUPS: Dict[str, List[dict]] = {
    "app_events": [
        {"label": "App Events", "filename": _DEBUG_FILE},
    ],
    "service_runtime": [
        {"label": "Service Runtime", "filename": "service_runtime.log"},
    ],
    "llama_server": [
        {"label": "Qwen Server", "filename": "llama_server_8082.log"},
        {"label": "App Fallback Server", "filename": "llama_server.log"},
        {"label": "Nomic Server", "filename": "nomic_server.log"},
    ],
    "crash": [
        {"label": "Crash Log", "filename": "crash.log"},
    ],
    "debug_notes": [
        {"label": "Llama Debug Notes", "filename": "llama_debug.txt"},
    ],
}

def _base_dir() -> str:
    base = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))
    os.makedirs(base, exist_ok=True)
    return base

def _env_truthy(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

def is_debug_logger_enabled() -> bool:
    return _env_truthy("ORAG_DEBUG_LOGGER", default=True)

def _debug_log_path() -> str:
    return os.path.join(_base_dir(), _DEBUG_FILE)

def _sanitize(text: str) -> str:
    return str(text).replace("\r", " ").replace("\n", " | ")

def debug_log(source: str, message: str, level: str = "INFO") -> None:
    if not is_debug_logger_enabled():
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    src = _sanitize(source)[:24].ljust(24)
    lvl = _sanitize(level).upper()[:8].ljust(8)
    msg = _sanitize(message)
    line = f"{ts} | {lvl} | {src} | {msg}\n"
    path = _debug_log_path()
    with _LOCK:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

def _resolve_entries(source_key: str) -> List[dict]:
    if source_key == "all":
        merged: List[dict] = []
        for key in ("app_events", "service_runtime", "llama_server", "crash", "debug_notes"):
            merged.extend(_SOURCE_GROUPS.get(key, []))
        return merged
    return list(_SOURCE_GROUPS.get(source_key, []))

def list_log_sources() -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for key in ("all", "app_events", "service_runtime", "llama_server", "crash", "debug_notes"):
        entries = _resolve_entries(key)
        out[key] = [
            {
                "label": e["label"],
                "filename": e["filename"],
                "path": os.path.join(_base_dir(), e["filename"]),
            }
            for e in entries
        ]
    return out

def _read_tail(path: str, max_bytes: int) -> str:
    if not os.path.isfile(path):
        return "No logs yet (file missing)."
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            data = f.read()
        return data.decode("utf-8", errors="replace").strip() or "(file is empty)"
    except Exception as exc:
        return f"Failed to read log: {exc}"

def tail_logs(source_key: str = "all", max_bytes_per_file: int = 64 * 1024, max_lines: int = 800) -> str:
    groups = list_log_sources()
    entries = groups.get(source_key, [])
    if not entries:
        return "No logs yet."
    sections: List[str] = []
    for e in entries:
        body = _read_tail(e["path"], max(2048, int(max_bytes_per_file)))
        header = f"===== {e['label']} ({e['filename']}) ====="
        sections.append(f"{header}\n{body}")
    text = "\n\n".join(sections).strip()
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines).strip() or "No logs yet."