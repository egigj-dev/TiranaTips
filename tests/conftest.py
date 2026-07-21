"""
conftest.py — mock heavy ML imports before main.py is loaded.

The offline chat tests (test_chat_api.py) need to import `main.py`, which in
turn imports langchain_huggingface, fastembed, optimum, transformers,
qdrant_client, sentence_transformers, and numpy. These packages are heavy
(~2GB) and may not be installed in every dev environment. This conftest
stubs them as empty modules before the test collector hits the import, so
the suite runs with zero ML dependencies.

The test's own monkeypatch fixtures replace the actual functions
(stream_llm_tokens, translate_question_to_english, etc.) later, so the
stubs only need to exist — they never get called.
"""
import sys
import types


# ---- callable stub that accepts any init args and returns itself on call ----
class _Stub:
    """A universal stub: instantiate it, call it, get any attr — never crashes."""
    def __init__(self, *args, **kwargs):
        pass
    def __call__(self, *args, **kwargs):
        return self
    def __getattr__(self, name):
        # Return a fresh stub for any attribute access.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _Stub()
    def __getitem__(self, key):
        return _Stub()
    def __setitem__(self, key, value):
        pass
    def __iter__(self):
        return iter([])
    def __len__(self):
        return 0
    def __bool__(self):
        return False


def _stub_module(name, exports=None):
    """Create or retrieve a minimal module stub with the given exports."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    if exports:
        for exp in exports:
            setattr(mod, exp, _Stub())
    sys.modules[name] = mod
    return mod


# The exact symbols main.py imports from each heavy module.
_stub_module("numpy")
_stub_module("sentence_transformers")
_stub_module("transformers", exports=["AutoTokenizer"])
_stub_module("transformers.utils")
_stub_module("optimum")
_stub_module("optimum.onnxruntime", exports=["ORTModelForSequenceClassification"])
_stub_module("qdrant_client", exports=["QdrantClient"])
_stub_module("qdrant_client.models", exports=[
    "Distance", "VectorParams", "SparseVector",
    "SparseVectorParams", "SparseIndexParams", "PointStruct",
    "Filter", "FieldCondition", "MatchValue", "MatchAny", "Range",
])
_stub_module("langchain_huggingface", exports=["HuggingFaceEmbeddings"])
_stub_module("langchain_text_splitters", exports=["RecursiveCharacterTextSplitter", "MarkdownHeaderTextSplitter"])
_stub_module("fastembed", exports=["SparseTextEmbedding"])

# city_notes.py imports these
_stub_module("bs4", exports=["BeautifulSoup"])

# apscheduler
_stub_module("apscheduler")
_stub_module("apscheduler.schedulers")
_stub_module("apscheduler.schedulers.asyncio", exports=["AsyncIOScheduler"])