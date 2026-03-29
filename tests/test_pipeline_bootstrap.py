from app.rag import pipeline


class _LoadedRuntime:
    def is_loaded(self) -> bool:
        return True

    def connect_external_server(self, model_path: str) -> None:  # pragma: no cover - not used in this case
        _ = model_path


def test_pipeline_register_callbacks_immediately_ready_when_loaded(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "runtime", _LoadedRuntime())

    done_events: list[tuple[bool, str]] = []
    pipeline.register_auto_download_callbacks(
        on_progress=None,
        on_done=lambda ok, msg: done_events.append((ok, msg)),
    )

    assert done_events
    assert done_events[-1][0] is True
