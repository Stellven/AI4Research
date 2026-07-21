#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate semantic layer architecture bridge closeout.")
    parser.add_argument("--runtime-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).expanduser().resolve()
    sys.path.insert(0, str(runtime_root / "lib"))
    from semantic_layer_architecture_bridge_closeout import main as closeout_main  # noqa: WPS433

    return closeout_main([str(runtime_root)])


if __name__ == "__main__":
    raise SystemExit(main())
