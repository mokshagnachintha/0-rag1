from app.runtime.bootstrap import BootstrapCoordinator, BootstrapState


def test_bootstrap_state_transitions_emit_callbacks() -> None:
    coordinator = BootstrapCoordinator()

    progress_events: list[tuple[float, str]] = []
    done_events: list[tuple[bool, str]] = []

    coordinator.register_callbacks(
        on_progress=lambda frac, msg: progress_events.append((frac, msg)),
        on_done=lambda ok, msg: done_events.append((ok, msg)),
    )

    coordinator.emit_downloading(0.3, "downloading")
    coordinator.emit_ready("ready")

    assert progress_events[-1] == (0.3, "downloading")
    assert done_events[-1] == (True, "ready")
    assert coordinator.event().state == BootstrapState.READY


def test_late_subscriber_gets_latest_state() -> None:
    coordinator = BootstrapCoordinator()
    coordinator.emit_error("boom")

    done_events: list[tuple[bool, str]] = []
    coordinator.register_callbacks(on_progress=None, on_done=lambda ok, msg: done_events.append((ok, msg)))

    assert done_events == [(False, "boom")]
