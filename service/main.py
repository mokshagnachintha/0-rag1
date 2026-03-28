"""
service/main.py  -  O-RAG Android foreground service.

Runs as a separate process and owns the Qwen llama-server process.
It waits until models are available and keeps the server alive.
"""
import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional


# ------------------------------------------------------------------ #
#  Android plumbing                                                  #
# ------------------------------------------------------------------ #

def _set_foreground():
    """Promote this service to foreground so Android will not kill it."""
    try:
        from jnius import autoclass  # type: ignore

        PythonService = autoclass("org.kivy.android.PythonService")
        NotifBuilder = autoclass("android.app.Notification$Builder")
        NotifManager = autoclass("android.app.NotificationManager")
        NotifChannel = autoclass("android.app.NotificationChannel")
        Context = autoclass("android.content.Context")
        Build = autoclass("android.os.Build")

        service = PythonService.mService

        channel_id = "orag_ai_channel"
        if Build.VERSION.SDK_INT >= 26:
            ch = NotifChannel(
                channel_id,
                "O-RAG AI Engine",
                NotifManager.IMPORTANCE_LOW,
            )
            nm = service.getSystemService(Context.NOTIFICATION_SERVICE)
            nm.createNotificationChannel(ch)

        builder = NotifBuilder(service, channel_id)
        builder.setContentTitle("O-RAG AI Engine")
        builder.setContentText("AI engine running in background")
        builder.setSmallIcon(service.getApplicationInfo().icon)
        builder.setOngoing(True)

        service.startForeground(1, builder.build())
        print("[service] Foreground notification set.")
    except Exception as exc:
        print(f"[service] _set_foreground skipped: {exc}")


# ------------------------------------------------------------------ #
#  Paths                                                             #
# ------------------------------------------------------------------ #

def _models_dir() -> str:
    base = os.environ.get("ANDROID_PRIVATE", os.path.expanduser("~"))
    path = os.path.join(base, "models")
    os.makedirs(path, exist_ok=True)
    return path


def _runtime_log_path() -> Optional[str]:
    priv = os.environ.get("ANDROID_PRIVATE", "")
    if not priv:
        return None
    return os.path.join(priv, "service_runtime.log")


def _log(msg: str) -> None:
    print(msg)
    path = _runtime_log_path()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _server_exe() -> Optional[Path]:
    """Locate llama-server binary."""
    if os.environ.get("ANDROID_PRIVATE"):
        # Service process must prefer nativeLibraryDir; app-private files may be noexec.
        try:
            from jnius import autoclass  # type: ignore

            PythonService = autoclass("org.kivy.android.PythonService")
            svc = PythonService.mService
            native_dir = str(svc.getApplicationInfo().nativeLibraryDir)
            so = Path(native_dir) / "libllama_server.so"
            if so.exists():
                _log(f"[service] Using native llama-server: {so}")
                return so
            _log(f"[service] libllama_server.so missing in {native_dir}")
        except Exception as exc:
            _log(f"[service] Failed reading PythonService nativeLibraryDir: {exc}")

        # Fallback: some builds expose only PythonActivity path.
        try:
            from jnius import autoclass  # type: ignore

            ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            native_dir = str(ctx.getApplicationInfo().nativeLibraryDir)
            so = Path(native_dir) / "libllama_server.so"
            if so.exists():
                _log(f"[service] Using activity native llama-server: {so}")
                return so
            _log(f"[service] Activity native lib missing: {so}")
        except Exception as exc:
            _log(f"[service] Failed reading PythonActivity nativeLibraryDir: {exc}")

        return None

    root = Path(__file__).resolve().parent.parent
    for name in ("llama-server-arm64", "llama-server", "llama-server.exe"):
        candidate = root / name
        if candidate.exists():
            return candidate

    return None


# ------------------------------------------------------------------ #
#  Helpers                                                           #
# ------------------------------------------------------------------ #

def _optimal_threads() -> int:
    try:
        count = os.cpu_count() or 4
        return max(2, min(8, count // 2))
    except Exception:
        return 4


def _probe(port: int) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _wait(port: int, timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _probe(port):
            return True
        time.sleep(1)
    return False


def _wait_with_process(port: int, proc: Optional[subprocess.Popen], timeout: int = 180) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            _log(f"[service] llama-server exited early (code={proc.returncode}) on port {port}")
            return False
        if _probe(port):
            return True
        time.sleep(1)
    return False


def _launch(
    model_path: str,
    port: int,
    n_ctx: int = 2048,
    extra_flags: Optional[List[str]] = None,
) -> Optional[subprocess.Popen]:
    exe = _server_exe()
    if exe is None:
        _log("[service] llama-server binary not found.")
        return None

    threads = _optimal_threads()
    cmd = [
        str(exe),
        "--model",
        model_path,
        "--ctx-size",
        str(n_ctx),
        "--threads",
        str(threads),
        "--threads-batch",
        str(threads),
        "--port",
        str(port),
        "--host",
        "127.0.0.1",
        "--embedding",
    ]
    if extra_flags:
        cmd.extend(extra_flags)

    _log(f"[service] Launching llama-server on port {port}: {Path(model_path).name}")
    priv = os.environ.get("ANDROID_PRIVATE", "")
    log_path = os.path.join(priv, f"llama_server_{port}.log") if priv else os.devnull
    try:
        lf = open(log_path, "wb") if log_path != os.devnull else subprocess.DEVNULL
        proc = subprocess.Popen(cmd, stdout=lf, stderr=lf)
        if lf not in (None, subprocess.DEVNULL):
            try:
                lf.close()
            except Exception:
                pass
        return proc
    except Exception as exc:
        _log(f"[service] Popen failed: {exc}")
        return None


def _tail_log(path: str, max_bytes: int = 4000) -> str:
    try:
        if not os.path.isfile(path):
            return ""
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


# ------------------------------------------------------------------ #
#  Main service loop                                                 #
# ------------------------------------------------------------------ #

QWEN_PORT = 8082
NOMIC_PORT = 8083
try:
    # Keep service filenames aligned with downloader manifest.
    from rag.downloader import NOMIC_MODEL, QWEN_MODEL  # type: ignore

    QWEN_FILE = str(QWEN_MODEL["filename"])
    NOMIC_FILE = str(NOMIC_MODEL["filename"])
except Exception:
    QWEN_FILE = "qwen2.5-1.5b-instruct-compressed.gguf"
    NOMIC_FILE = "nomic-embed-text-v1.5-compressed.gguf"
MIN_QWEN_BYTES = 100 * 1024 * 1024
MIN_NOMIC_BYTES = 10 * 1024 * 1024


def _wait_for_models(qwen_path: str):
    """Block until Qwen model file is on disk.
    Nomic is started lazily by the app on first PDF upload.
    """
    while True:
        qwen_ok = os.path.isfile(qwen_path) and os.path.getsize(qwen_path) > MIN_QWEN_BYTES
        if qwen_ok:
            _log("[service] Qwen model file ready.")
            return
        _log("[service] Waiting for Qwen model file...")
        time.sleep(5)


def main():
    _log("[service] O-RAG AI service starting.")
    # p4a promotes :foreground services automatically; do not call startForeground twice.

    models = _models_dir()
    qwen_path = os.path.join(models, QWEN_FILE)
    nomic_path = os.path.join(models, NOMIC_FILE)

    _log(f"[service] Expected Qwen file: {qwen_path}")
    _log(f"[service] Expected Nomic file: {nomic_path}")
    _wait_for_models(qwen_path)

    qwen_proc = None

    while True:
        if qwen_proc is None or qwen_proc.poll() is not None:
            if not _probe(QWEN_PORT):
                _log(f"[service] Starting Qwen server (port {QWEN_PORT})...")
                qwen_proc = _launch(qwen_path, QWEN_PORT, n_ctx=768)
                if qwen_proc and _wait_with_process(QWEN_PORT, qwen_proc, timeout=180):
                    _log(f"[service] Qwen server ready on port {QWEN_PORT}.")
                else:
                    _log("[service] Qwen server failed to start.")
                    priv = os.environ.get("ANDROID_PRIVATE", "")
                    if priv:
                        tail = _tail_log(os.path.join(priv, f"llama_server_{QWEN_PORT}.log"))
                        if tail:
                            _log(f"[service] llama-server log tail:\n{tail}")
                    qwen_proc = None
            else:
                _log("[service] Qwen server already responding - reusing.")

        time.sleep(10)


if __name__ == "__main__":
    main()

