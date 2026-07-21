"""Solar-managed launcher for the vendored MIA Memory-Serve Flask service.

Applies three in-memory patches to memory_serve.py without touching the
vendor source tree:

  1. BERT path   — reads MIA_BERT_PATH env var (defaults to the locally
                   cached all-MiniLM-L6-v2 HuggingFace snapshot).
  2. LLM shim    — llm_get_trace returns the raw trace when MEMORY_URL is
                   unset, enabling local smoke-testing without an LLM backend.
  3. Shim import — memory_functions resolves to the Solar compatibility shim
                   in lib/experience/ instead of the missing upstream file.

Run as:
    venvs/mia-memory-serve/bin/python3 lib/experience/memory_serve_wrapper.py \
        --host 127.0.0.1 --port 5197
"""
from __future__ import annotations

import argparse
import os
import sys
import types

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HARNESS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
MIA_DIR = os.path.join(HARNESS_DIR, "vendor", "MIA", "Memory-Serve")
SHIM_DIR = os.path.dirname(os.path.abspath(__file__))  # lib/experience/

_DEFAULT_BERT = os.path.join(
    os.path.expanduser("~"),
    ".cache",
    "huggingface",
    "hub",
    "models--sentence-transformers--all-MiniLM-L6-v2",
    "snapshots",
    "c9745ed1d9f207416be6d2e6f8de32d1f16199bf",
)

# ---------------------------------------------------------------------------
# In-memory patching
# ---------------------------------------------------------------------------

_BERT_ORIGINAL = '        bert_path = "/your_path/bert/sup-simcse-bert-base-uncased"'
_BERT_PATCHED = (
    '        bert_path = os.environ.get('
    '"MIA_BERT_PATH", "/your_path/bert/sup-simcse-bert-base-uncased")'
)

_TRACE_ORIGINAL = "    # return trace\n    \n    prompt = get_trace_prompt.format(trace=trace)"
_TRACE_PATCHED = (
    '    # return trace\n'
    '    if not os.getenv("MEMORY_URL"):\n'
    '        return trace\n'
    '    prompt = get_trace_prompt.format(trace=trace)'
)


def _load_patched_module() -> types.ModuleType:
    """Read memory_serve.py, apply patches, exec in a fresh module namespace."""
    # Shim directory must come before MIA_DIR so memory_functions.py shim wins
    sys.path.insert(0, SHIM_DIR)
    sys.path.insert(0, MIA_DIR)

    src_path = os.path.join(MIA_DIR, "memory_serve.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()

    assert _BERT_ORIGINAL in src, "BERT patch anchor not found — vendor source changed?"
    src = src.replace(_BERT_ORIGINAL, _BERT_PATCHED)

    assert _TRACE_ORIGINAL in src, "llm_get_trace patch anchor not found — vendor source changed?"
    src = src.replace(_TRACE_ORIGINAL, _TRACE_PATCHED)

    mod = types.ModuleType("memory_serve")
    mod.__file__ = src_path
    mod.__package__ = ""
    code = compile(src, src_path, "exec")
    exec(code, mod.__dict__)  # noqa: S102
    sys.modules["memory_serve"] = mod
    return mod


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MIA Memory-Serve (Solar wrapper)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5197)
    parser.add_argument("--model_name", default=None)
    args = parser.parse_args()

    os.environ.setdefault("MIA_BERT_PATH", _DEFAULT_BERT)

    ms = _load_patched_module()

    if args.model_name:
        ms.MODEL_NAME = args.model_name

    # Instantiate the processor (initialises BERT model)
    ms.processor = ms.MemoryProcessor()

    # Start Flask (blocking)
    ms.app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
