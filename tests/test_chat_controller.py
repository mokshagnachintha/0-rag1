from app.ui.chat.controller import ChatController


class _Calls:
    def __init__(self) -> None:
        self.called = []

    def add(self, name: str, *args, **kwargs) -> None:
        self.called.append((name, args, kwargs))


def test_controller_document_management_actions(monkeypatch) -> None:
    from app.ui.chat import actions

    calls = _Calls()

    monkeypatch.setattr(actions, "list_documents", lambda: [{"id": 1, "name": "a.pdf"}])
    monkeypatch.setattr(actions, "delete_document", lambda doc_id: calls.add("delete", doc_id))
    monkeypatch.setattr(actions, "clear_documents", lambda: calls.add("clear"))

    controller = ChatController()

    docs = controller.list_documents()
    controller.delete_document(9)
    controller.clear_documents()

    assert docs == [{"id": 1, "name": "a.pdf"}]
    assert ("delete", (9,), {}) in calls.called
    assert ("clear", (), {}) in calls.called


def test_controller_bootstrap_state_passthrough(monkeypatch) -> None:
    from app.ui.chat import actions

    state = object()
    monkeypatch.setattr(actions, "get_bootstrap_state", lambda: state)

    controller = ChatController()
    assert controller.get_bootstrap_state() is state
