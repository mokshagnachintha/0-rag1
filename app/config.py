"""
Shared configuration and constants for the offline RAG app.
"""
from __future__ import annotations

import os


APP_NAME = "O-RAG"
SERVICE_TITLE = "O-RAG AI Engine"
SERVICE_MESSAGE = "AI engine running in background"

QWEN_SERVER_PORT = 8082
NOMIC_SERVER_PORT = 8083

ENV_FORCE_BOOTSTRAP_DOWNLOAD = "ORAG_FORCE_BOOTSTRAP_DOWNLOAD"
ENV_FORCE_NETWORK_MODEL_DOWNLOAD = "ORAG_FORCE_NETWORK_MODEL_DOWNLOAD"


def env_truthy(name: str) -> bool:
    val = os.environ.get(name, "")
    return str(val).strip().lower() in {"1", "true", "yes", "on"}
