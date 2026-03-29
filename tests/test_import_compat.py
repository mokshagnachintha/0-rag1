import importlib
import warnings


def test_rag_shim_imports_work_and_warn() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        chunker_mod = importlib.import_module("rag.chunker")
        pipeline_mod = importlib.import_module("rag.pipeline")

    assert hasattr(chunker_mod, "tokenise")
    assert hasattr(pipeline_mod, "register_auto_download_callbacks")
    assert any("deprecated" in str(w.message).lower() for w in caught)
