"""
Runtime abstraction for model loading, generation, embeddings and health.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Callable

from app.rag.llm import (
    llm,
    get_embedding,
    list_available_models,
    probe_port,
    qwen_port,
    nomic_port,
    start_nomic_server,
)


@dataclass(frozen=True)
class RuntimeHealth:
    qwen_ready: bool
    nomic_ready: bool
    backend: str
    model_path: str


class ModelRuntime(Protocol):
    def load(
        self,
        model_path: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> None: ...

    def connect_external_server(self, model_path: str) -> None: ...

    def generate(self, prompt: str, stream_cb: Optional[Callable[[str], None]] = None) -> str: ...

    def embedding(self, text: str) -> list[float] | None: ...

    def health(self) -> RuntimeHealth: ...

    def shutdown(self) -> None: ...

    def is_loaded(self) -> bool: ...

    def model_path(self) -> str: ...

    def backend(self) -> str: ...


class LlamaModelRuntime:
    def load(
        self,
        model_path: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        llm.load(model_path, on_progress=on_progress)

    def connect_external_server(self, model_path: str) -> None:
        llm.connect_external_server(model_path)

    def generate(self, prompt: str, stream_cb: Optional[Callable[[str], None]] = None) -> str:
        return llm.generate(prompt, stream_cb=stream_cb)

    def embedding(self, text: str) -> list[float] | None:
        return get_embedding(text)

    def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            qwen_ready=probe_port(qwen_port()),
            nomic_ready=probe_port(nomic_port()),
            backend=llm.backend_name,
            model_path=llm.model_path or "",
        )

    def shutdown(self) -> None:
        llm.unload()

    def is_loaded(self) -> bool:
        return llm.is_loaded()

    def model_path(self) -> str:
        return llm.model_path or ""

    def backend(self) -> str:
        return llm.backend_name

    def start_nomic_server_if_needed(self, model_path: str) -> None:
        if not probe_port(nomic_port()):
            start_nomic_server(model_path)

    def available_models(self) -> list[str]:
        return list_available_models()
