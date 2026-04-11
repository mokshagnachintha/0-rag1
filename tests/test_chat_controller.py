from app.ui.chat import controller as controller_mod
from app.ui.chat.controller import ChatController


class _FakeService:
    def __init__(self) -> None:
        self.calls = []
        self.state = object()

    def ensure_initialized(self) -> None:
        self.calls.append(("ensure_initialized", (), {}))

    def register_bootstrap_callbacks(self, on_progress, on_done) -> None:
        self.calls.append(("register_bootstrap_callbacks", (on_progress, on_done), {}))

    def get_bootstrap_state(self):
        return self.state

    def list_documents(self):
        return [{"id": 1, "name": "a.pdf"}]

    def delete_document(self, doc_id: int) -> None:
        self.calls.append(("delete_document", (doc_id,), {}))

    def clear_documents(self) -> None:
        self.calls.append(("clear_documents", (), {}))

    def ask(self, question, stream_cb=None, on_done=None):
        self.calls.append(("ask", (question,), {"stream_cb": stream_cb, "on_done": on_done}))
        return "task-rag"

    def chat_direct(self, question, history=None, summary="", stream_cb=None, on_done=None):
        self.calls.append(
            (
                "chat_direct",
                (question,),
                {
                    "history": history,
                    "summary": summary,
                    "stream_cb": stream_cb,
                    "on_done": on_done,
                },
            )
        )
        return "task-chat"



def test_controller_document_management_actions(monkeypatch) -> None:
    fake = _FakeService()
    monkeypatch.setattr(controller_mod, "get_chat_service", lambda: fake)

    controller = ChatController()

    docs = controller.list_documents()
    controller.delete_document(9)
    controller.clear_documents()
    rag_task = controller.ask("hello")
    chat_task = controller.chat_direct("hi")

    assert docs == [{"id": 1, "name": "a.pdf"}]
    assert rag_task == "task-rag"
    assert chat_task == "task-chat"
    assert ("delete_document", (9,), {}) in fake.calls
    assert ("clear_documents", (), {}) in fake.calls


def test_controller_bootstrap_state_passthrough(monkeypatch) -> None:
    fake = _FakeService()
    monkeypatch.setattr(controller_mod, "get_chat_service", lambda: fake)

    controller = ChatController()
    assert controller.get_bootstrap_state() is fake.state
