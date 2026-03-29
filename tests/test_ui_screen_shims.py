import importlib
import warnings


def test_ui_screen_shims_warn_on_import() -> None:
    modules = [
        "ui.screens.chat_screen",
        "ui.screens.docs_screen",
        "ui.screens.settings_screen",
    ]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for module in modules:
            importlib.import_module(module)

    messages = [str(w.message).lower() for w in caught]
    assert any("chat_screen" in msg and "deprecated" in msg for msg in messages)
    assert any("docs_screen" in msg and "deprecated" in msg for msg in messages)
    assert any("settings_screen" in msg and "deprecated" in msg for msg in messages)
