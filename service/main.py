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

from app.config import NOMIC_SERVER_PORT, QWEN_SERVER_PORT


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


def _server_exe() -> Optional[Path]:
    """Locate llama-server binary."""
    try:
        from jnius import autoclass  # type: ignore

        ctx = autoclass("org.kivy.android.PythonActivity").mActivity
        native_dir = ctx.getApplicationInfo().nativeLibraryDir
        so = Path(native_dir) / "libllama_server.so"
        if so.exists():
            return so
    except Exception:
        pass

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


def _launch(
    model_path: str,
    port: int,
    n_ctx: int = 2048,
    extra_flags: Optional[List[str]] = None,
) -> Optional[subprocess.Popen]:
    exe = _server_exe()
    if exe is None:
        print("[service] llama-server binary not found.")
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
        "--flash-attn",
        "on",
        "--cache-type-k",
        "q8_0",
        "--cache-type-v",
        "q8_0",
        "--cont-batching",
    ]
    if extra_flags:
        cmd.extend(extra_flags)

    print(f"[service] Launching llama-server on port {port}: {Path(model_path).name}")
    priv = os.environ.get("ANDROID_PRIVATE", "")
    log_path = os.path.join(priv, f"llama_server_{port}.log") if priv else os.devnull
    try:
        lf = open(log_path, "wb") if log_path != os.devnull else subprocess.DEVNULL
        return subprocess.Popen(cmd, stdout=lf, stderr=lf)
    except Exception as exc:
        print(f"[service] Popen failed: {exc}")
        return None


# ------------------------------------------------------------------ #
#  Main service loop                                                 #
# ------------------------------------------------------------------ #

QWEN_PORT = QWEN_SERVER_PORT
NOMIC_PORT = NOMIC_SERVER_PORT
QWEN_FILE = "qwen2.5-1.5b-instruct-compressed.gguf"
NOMIC_FILE = "nomic-embed-text-v1.5-compressed.gguf"
MIN_QWEN_BYTES = 100 * 1024 * 1024
MIN_NOMIC_BYTES = 10 * 1024 * 1024


def _wait_for_models(qwen_path: str, nomic_path: str):
    """Block until Qwen model file is on disk.
    Nomic is started lazily by the app on first PDF upload.
    """
    while True:
        qwen_ok = os.path.isfile(qwen_path) and os.path.getsize(qwen_path) > MIN_QWEN_BYTES
        if qwen_ok:
            print("[service] Qwen model file ready.")
            return
        print("[service] Waiting for Qwen model file...")
        time.sleep(5)


def main():
    print("[service] O-RAG AI service starting.")
    # p4a promotes :foreground services automatically; do not call startForeground twice.

    models = _models_dir()
    qwen_path = os.path.join(models, QWEN_FILE)
    nomic_path = os.path.join(models, NOMIC_FILE)

    _wait_for_models(qwen_path, nomic_path)

    qwen_proc = None

    while True:
        if qwen_proc is None or qwen_proc.poll() is not None:
            if not _probe(QWEN_PORT):
                print(f"[service] Starting Qwen server (port {QWEN_PORT})...")
                qwen_proc = _launch(qwen_path, QWEN_PORT, n_ctx=768)
                if qwen_proc and _wait(QWEN_PORT, timeout=180):
                    print(f"[service] Qwen server ready on port {QWEN_PORT}.")
                else:
                    print("[service] Qwen server failed to start.")
                    qwen_proc = None
            else:
                print("[service] Qwen server already responding - reusing.")

        time.sleep(10)


if __name__ == "__main__":
    main()

